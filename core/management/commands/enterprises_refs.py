"""
Command to seed enterprises.

Usage: python manage.py enterprises_refs

Requer cidades já populadas (rode antes: python manage.py state_and_city).
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from core.models import City
from enterprises.models import Enterprise


# Preencha os valores abaixo (um dict por empresa).
#   name   -> obrigatório
#   cnpj   -> obrigatório, 14 dígitos (pode vir com máscara; só os dígitos são salvos)
#   city   -> obrigatório, nome da cidade (deve existir no banco)
#   state  -> opcional, sigla da UF — desambigua cidades de mesmo nome
#   sap_code / contact / email -> opcionais
ENTERPRISES = [
    {
        "name": "Rotoline",
        "cnpj": "12.345.678/0001-90",
        "city": "Concórdia",
        "state": "SC",
        "sap_code": "33432",
        "contact": "4933245680",
        "email": "rotoline@rotoline.com",
    },
]


class Command(BaseCommand):
    help = 'Seed the database with enterprises'

    def handle(self, *args, **options):
        self.stdout.write('Starting enterprises seed...')

        created = 0
        skipped = 0

        for data in ENTERPRISES:
            name = data['name']
            cnpj = ''.join(filter(str.isdigit, data.get('cnpj', '')))

            # ----- Resolve a cidade (FK obrigatória) -----
            city_qs = City.objects.filter(name=data['city'])
            if data.get('state'):
                city_qs = city_qs.filter(state__acronym=data['state'])

            city = city_qs.first()
            if city is None:
                self.stdout.write(f'  [SKIP] Cidade não encontrada para "{name}": {data["city"]}')
                skipped += 1
                continue
            if city_qs.count() > 1:
                self.stdout.write(
                    f'  [SKIP] Cidade ambígua para "{name}": {data["city"]} '
                    f'(informe "state" para desambiguar)'
                )
                skipped += 1
                continue

            if Enterprise.objects.filter(cnpj=cnpj).exists():
                self.stdout.write(f'  - Já existe: {name} ({cnpj})')
                continue

            enterprise = Enterprise(
                name=name,
                cnpj=cnpj,
                city=city,
                sap_code=data.get('sap_code') or None,
                contact=data.get('contact') or None,
                email=data.get('email') or None,
                image_url=data.get('image_url') or None,
            )

            try:
                enterprise.full_clean()
                enterprise.save()
            except ValidationError as exc:
                self.stdout.write(f'  [ERRO] Falhou "{name}": {exc.message_dict}')
                skipped += 1
                continue

            created += 1
            self.stdout.write(f'  [OK] Enterprise: {name} ({cnpj}) - {city.name}')

        self.stdout.write('')
        self.stdout.write('Enterprises seed completed!')
        self.stdout.write(f'  Created: {created}')
        self.stdout.write(f'  Skipped: {skipped}')
        self.stdout.write(f'  Enterprise total: {Enterprise.objects.count()}')
