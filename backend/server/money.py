from decimal import Decimal, InvalidOperation


VALID_CURRENCIES = set(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND
    BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUC CUP CVE CZK
    DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
    HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF
    KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP
    MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP
    PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS
    SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD
    UYU UZS VES VND VUV WST XAF XCD XCG XDR XOF XPF XSU YER ZAR ZMW ZWG ZWL
    """
    .split()
)
ZERO_DECIMAL_CURRENCIES = {
    "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG",
    "RWF", "UGX", "UYI", "VND", "VUV", "XAF", "XOF", "XPF",
}
THREE_DECIMAL_CURRENCIES = {
    "BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND",
}


def currency_precision(currency):
    if not isinstance(currency, str) or currency not in VALID_CURRENCIES:
        return None
    if currency in ZERO_DECIMAL_CURRENCIES:
        return 0
    if currency in THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def parse_money(value, currency, *, allow_zero=False):
    precision = currency_precision(currency)
    if precision is None:
        return None, "Property currency must be a three-letter uppercase code"
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None, "Amount must be a number"
    try:
        amount = Decimal(str(value))
        quantum = Decimal(1).scaleb(-precision)
        if not amount.is_finite():
            raise InvalidOperation
        if amount < 0 or (not allow_zero and amount == 0):
            return None, "Amount must be a positive number"
        if amount != amount.quantize(quantum):
            return None, f"Amount must have no more than {precision} decimal places"
        amount = amount.quantize(quantum)
    except InvalidOperation:
        return None, f"Amount must have no more than {precision} decimal places"
    if amount >= Decimal("1000000000"):
        return None, "Amount is too large"
    return amount, None
