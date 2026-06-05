from rest_framework import serializers

from .models import Enterprise


class EnterpriseSerializer(serializers.ModelSerializer):
    # Dados de localizacao (somente leitura, derivados da city)
    city_name = serializers.CharField(source="city.name", read_only=True)
    state_name = serializers.CharField(source="city.state.name", read_only=True)
    country_name = serializers.CharField(source="city.state.country.name", read_only=True)

    class Meta:
        model = Enterprise
        fields = [
            "id",
            "name",
            "cnpj",
            "sap_code",
            "contact",
            "email",
            "image_url",
            "city",
            "city_name",
            "state_name",
            "country_name",
        ]

    def validate_cnpj(self, value):
        """Remove a mascara, mantendo apenas os digitos antes de salvar."""
        return ''.join(filter(str.isdigit, value or ''))
