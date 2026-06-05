from rest_framework import serializers

from .models import Country, State, City


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "name", "acronym"]


class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = State
        fields = ["id", "name", "acronym", "country", "country_name"]


class CitySerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    country = serializers.PrimaryKeyRelatedField(source="state.country", read_only=True)
    country_name = serializers.CharField(source="state.country.name", read_only=True)

    class Meta:
        model = City
        fields = ["id", "name", "state", "state_name", "country", "country_name"]
