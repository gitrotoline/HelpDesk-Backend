from django.core.exceptions import ValidationError


def validate_cnpj(value):
    """Valida um CNPJ (apenas digitos, 14 posicoes, com digitos verificadores)."""
    cnpj = ''.join(filter(str.isdigit, value or ''))

    if len(cnpj) != 14:
        raise ValidationError('CNPJ deve conter 14 digitos.')

    # Rejeita sequencias de digitos iguais (ex.: 00000000000000)
    if cnpj == cnpj[0] * 14:
        raise ValidationError('CNPJ invalido.')

    def calc_digit(base, weights):
        total = sum(int(d) * w for d, w in zip(base, weights))
        rest = total % 11
        return '0' if rest < 2 else str(11 - rest)

    first = calc_digit(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = calc_digit(cnpj[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])

    if cnpj[-2:] != first + second:
        raise ValidationError('CNPJ invalido.')
