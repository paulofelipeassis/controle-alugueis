"""Regras puras: datas, dinheiro e situações. Nada aqui acessa o banco."""
import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sistema import config


def maiuscula(texto):
    return texto[:1].upper() + texto[1:]


class ErroDeNegocio(Exception):
    """Erro com mensagem em português, para mostrar à pessoa ou ao Hermes."""


# --- DATA E HORA ---
def agora():
    return datetime.now(ZoneInfo(config.TZ)).strftime("%Y-%m-%d %H:%M:%S")


def hoje():
    return datetime.now(ZoneInfo(config.TZ)).date()


def para_data(valor, campo="data"):
    """Aceita date, 'AAAA-MM-DD' ou 'DD/MM/AAAA'."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    raise ErroDeNegocio(f"{maiuscula(campo)} inválida: '{texto}'. Use o formato AAAA-MM-DD.")


def somar_meses(data, meses):
    total = data.year * 12 + data.month - 1 + meses
    ano, mes = divmod(total, 12)
    mes += 1
    return date(ano, mes, min(data.day, calendar.monthrange(ano, mes)[1]))


# --- COMPETÊNCIA E VENCIMENTO ---
def validar_competencia(valor):
    """Aceita 'AAAA-MM' ou 'MM/AAAA'; devolve 'AAAA-MM'."""
    texto = str(valor or "").strip()
    m = re.fullmatch(r"(\d{2})/(\d{4})", texto)
    if m:
        texto = f"{m.group(2)}-{m.group(1)}"
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", texto):
        raise ErroDeNegocio(f"Competência inválida: '{valor}'. Use o formato AAAA-MM (ex.: 2026-10).")
    return texto


def competencia_de(data):
    return f"{data.year:04d}-{data.month:02d}"


def dias_do_mes(competencia):
    ano, mes = map(int, competencia.split("-"))
    return calendar.monthrange(ano, mes)[1]


def proxima_competencia(competencia):
    ano, mes = map(int, competencia.split("-"))
    return competencia_de(somar_meses(date(ano, mes, 1), 1))


def vencimento(competencia, dia):
    """Dia de vencimento naquele mês; se o mês não tem o dia, o último dia do mês."""
    ano, mes = map(int, competencia.split("-"))
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def primeira_competencia(data_inicio, dia_vencimento, inicio_cobrancas):
    """Competência do primeiro vencimento a partir do início, nunca antes de inicio_cobrancas."""
    competencia = competencia_de(data_inicio)
    if vencimento(competencia, dia_vencimento) < data_inicio:
        competencia = proxima_competencia(competencia)
    return max(competencia, inicio_cobrancas)


# --- DIA ÚTIL ---
# Vencimento que cai em dia sem expediente bancário (fim de semana ou feriado) vale até o dia útil
# seguinte, sem multa nem juros: regra dos boletos bancários, e o Código Civil (art. 132, §1º)
# prorroga para o dia útil seguinte o prazo que vence em feriado.
def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    mes, dia = divmod(h + ell - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def feriados(ano):
    """Feriados nacionais e dias sem expediente bancário no ano, mais os de config.FERIADOS_EXTRAS."""
    dias = {date(ano, m, d) for m, d in [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]}
    if ano >= 2024:  # Dia da Consciência Negra virou feriado nacional (Lei 14.759/2023)
        dias.add(date(ano, 11, 20))
    # 31/12: sem expediente bancário ao público, todo ano (Febraban; calendário da Resolução CMN 4.880/2020).
    dias.add(date(ano, 12, 31))
    p = pascoa(ano)
    dias |= {p - timedelta(days=48), p - timedelta(days=47),  # carnaval (segunda e terça)
             p - timedelta(days=2),                           # sexta-feira santa
             p + timedelta(days=60)}                          # corpus christi
    for item in filter(None, (x.strip() for x in config.FERIADOS_EXTRAS.split(","))):
        try:
            partes = [int(x) for x in item.split("-")]
            dias.add(date(ano, *partes) if len(partes) == 2 else date(*partes))
        except ValueError:
            raise ErroDeNegocio(f"FERIADOS_EXTRAS inválido: '{item}'. Use MM-DD ou AAAA-MM-DD.") from None
    return dias


def dia_util(data):
    return data.weekday() < 5 and data not in feriados(data.year)


def vencimento_efetivo(data):
    """Último dia para pagar sem multa e juros: o próprio vencimento, ou o primeiro dia útil depois dele."""
    while not dia_util(data):
        data += timedelta(days=1)
    return data


# --- DINHEIRO (sempre em centavos, inteiro) ---
def reais_para_centavos(valor, campo="valor"):
    """Aceita '1.234,56', '1234,56', '1234.56', '1234', 'R$ 1.234,56' ou número."""
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        texto = str(valor)
    else:
        texto = str(valor or "").replace("R$", "").replace(" ", "").strip()
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif texto.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", texto):
            # '1.234' ou '1.234.567': ponto como separador de milhar (padrão brasileiro).
            texto = texto.replace(".", "")
    try:
        reais = Decimal(texto)
    except InvalidOperation:
        raise ErroDeNegocio(f"{maiuscula(campo)} inválido: '{valor}'. Use o formato 1.234,56.") from None
    if reais < 0:
        raise ErroDeNegocio(f"{maiuscula(campo)} não pode ser negativo.")
    return int((reais * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def valor_proporcional(valor_centavos, dias, dias_no_mes):
    """Aluguel proporcional aos dias usados do mês (dias corridos, do mês civil), em centavos."""
    dias = max(0, min(int(dias), int(dias_no_mes)))
    return int((Decimal(int(valor_centavos)) * dias / int(dias_no_mes)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def formatar_reais(centavos):
    if centavos is None:
        return ""
    sinal = "-" if centavos < 0 else ""
    reais, cent = divmod(abs(int(centavos)), 100)
    return f"{sinal}R$ {reais:,}".replace(",", ".") + f",{cent:02d}"


def formatar_pct(valor):
    """'4.12' → '4,12'; '-2.10' → '-2,10'."""
    return f"{Decimal(str(valor)):.2f}".replace(".", ",")


def encargos(valor, multa_pct, juros_mes_pct, vencimento_, data):
    """(multa, juros) em centavos para pagamento em `data`. Juros pró-rata: juros% × dias ÷ 30."""
    if valor <= 0 or data <= vencimento_:
        return 0, 0
    dias = (data - vencimento_).days
    multa = Decimal(valor) * Decimal(str(multa_pct)) / 100
    juros = Decimal(valor) * Decimal(str(juros_mes_pct)) / 100 * dias / 30
    arred = lambda d: int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))  # noqa: E731
    return arred(multa), arred(juros)


# --- REAJUSTE ANUAL ---
INDICES = ("IPCA", "IGP-M")


def normalizar_indice(texto):
    """'igpm', 'IGP-M', 'Igp m' → 'IGP-M'; 'ipca' → 'IPCA'; outro → None."""
    chave = re.sub(r"[^A-Z]", "", str(texto or "").upper())
    return {"IPCA": "IPCA", "IGPM": "IGP-M"}.get(chave)


def proximo_aniversario(valor_vigente_desde):
    """Reajuste só pode ser anual (Lei 10.192/2001, art. 2º §1º): 12 meses depois do último valor."""
    return somar_meses(valor_vigente_desde, 12)


def acumulado_pct(variacoes_pct):
    """Variação acumulada (%) de uma sequência de variações mensais (%): produto de (1 + v/100)."""
    fator = Decimal(1)
    for v in variacoes_pct:
        fator *= 1 + Decimal(str(v)) / 100
    return ((fator - 1) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def valor_reajustado(valor, percentual):
    """Índice negativo ou zero mantém o valor (decisão do Paulo)."""
    percentual = Decimal(str(percentual))
    if percentual <= 0:
        return valor
    novo = Decimal(valor) * (1 + percentual / 100)
    return int(novo.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --- SITUAÇÕES (calculadas, nunca digitadas) ---
def situacao_cobranca(situacao, valor, pago, vencimento_, hoje_):
    if situacao in ("cancelada", "isenta"):
        return situacao
    if pago >= valor:
        return "paga"
    if vencimento_ < hoje_:
        return "atrasada"
    if pago > 0:
        return "parcial"
    return "em_aberto"


def situacao_imovel(tem_contrato_ativo, em_manutencao, inicio_no_futuro=False):
    """'reservado' = tem contrato ativo que ainda não começou (o imóvel segue vago até a data de início)."""
    if tem_contrato_ativo:
        return "reservado" if inicio_no_futuro else "alugado"
    return "em_manutencao" if em_manutencao else "vago"


# --- TEXTO ---
def so_digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))


def validar_cpf_cnpj(texto):
    digitos = so_digitos(texto)
    if len(digitos) not in (11, 14):
        raise ErroDeNegocio(f"CPF/CNPJ inválido: '{texto}'. O CPF tem 11 dígitos e o CNPJ tem 14.")
    return digitos


def chave_nome(texto):
    """Forma de comparar nomes ignorando acento, maiúscula e pontuação ('Anel Viário' = 'anel viario')."""
    return nome_pasta(texto).casefold()


def nome_pasta(texto):
    """Nome seguro para pasta: sem acento, sem caracteres proibidos, sem espaços repetidos."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r'[\\/:*?"<>|]', "", sem_acento)
    return re.sub(r"\s+", " ", limpo).strip(" .")
