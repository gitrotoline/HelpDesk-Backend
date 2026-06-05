"""
Command to seed states and cities based on customer data.

Usage: python manage.py state_and_city
Requirement: run `python manage.py country` first.
"""

from django.core.management.base import BaseCommand
from core.models import Country, State, City


# ============================================================
# DATA: (country_acronym, state_acronym, state_name, [cities])
# ============================================================

DATA = [
    # --------------------------------------------------------
    # BRASIL
    # --------------------------------------------------------
    ('BRA', 'PB', 'Paraiba', [
        'Esperanca',
    ]),
    ('BRA', 'RS', 'Rio Grande do Sul', [
        'Estacao',
        'Victor Graeff',
        'Erechim',
        'Caxias do Sul',
        'Marau',
        'Montenegro',
        'Vila Maria',
        'Carazinho',
        'Santa Cruz do Sul',
        'Santa Rosa',
        'Sao Leopoldo',
        'Horizontina',
        'Triunfo',
        'Passo Fundo',
    ]),
    ('BRA', 'SP', 'Sao Paulo', [
        'Ferraz de Vasconcelos',
        'Nova Alianca',
        'Pompeia',
        'Rio Claro',
        'Diadema',
        'Atibaia',
        'Itatiba',
        'Maua',
        'Cajamar',
        'Campinas',
        'Leme',
        'Boituva',
        'Guarulhos',
        'Jundiai',
        'Vinhedo',
        'Matao',
        'Sorocaba',
        'Aruja',
        'Itapira',
        'Cordeiropolis',
        'Barueri',
    ]),
    ('BRA', 'PR', 'Parana', [
        'Toledo',
        'Nova Santa Rosa',
        'Cascavel',
        'Sao Jose dos Pinhais',
        'Marechal Candido Rondon',
        'Marialva',
        'Fazenda Rio Grande',
        'Campina Grande do Sul',
        'Campo Mourao',
    ]),
    ('BRA', 'CE', 'Ceara', [
        'Aquiraz',
        'Caucaia',
    ]),
    ('BRA', 'PE', 'Pernambuco', [
        'Recife',
        'Cabo de Santo Agostinho',
        'Palmares',
        'Escada',
        'Vitoria de Santo Antao',
        'Bezerros',
    ]),
    ('BRA', 'BA', 'Bahia', [
        'Camacari',
        'Feira de Santana',
        'Jequie',
        'Simoes Filho',
    ]),
    ('BRA', 'ES', 'Espirito Santo', [
        'Serra',
    ]),
    ('BRA', 'SC', 'Santa Catarina', [
        'Araquari',
        'Chapeco',
        'Brusque',
        'Itajai',
        'Maravilha',
        'Guaramirim',
        'Balneario Picarras',
        'Xanxere',
    ]),
    ('BRA', 'RJ', 'Rio de Janeiro', [
        'Duque de Caxias',
        'Rio de Janeiro',
        'Tres Rios',
    ]),
    ('BRA', 'GO', 'Goias', [
        'Anapolis',
        'Catalao',
        'Goiania',
    ]),
    ('BRA', 'MG', 'Minas Gerais', [
        'Betim',
    ]),
    ('BRA', 'AM', 'Amazonas', [
        'Manaus',
    ]),
    ('BRA', 'MT', 'Mato Grosso', [
        'Varzea Grande',
        'Cuiaba',
    ]),

    # --------------------------------------------------------
    # USA
    # --------------------------------------------------------
    ('USA', 'IA', 'Iowa', [
        'Fleminburg',
        'Grinnell',
        'Belle Plaine',
        'Davenport',
        'Rock Valley',
        'Cascade',
    ]),
    ('USA', 'IN', 'Indiana', [
        'Grabill',
        'Elkhart',
        'Columbia City',
        'Bristol',
        'New Paris',
        'Mishawaka',
        'Angola',
        'Yoder',
        'Elberfeld',
        'Goshen',
    ]),
    ('USA', 'MN', 'Minnesota', [
        'Benson',
        'West Point',
        'Baxter',
        'Little Falls',
        'Hoyt Lakes',
        'Cannon Falls',
        'Maple Plain',
        'Nicollet',
        'Brainerd',
    ]),
    ('USA', 'TN', 'Tennessee', [
        'Crossville',
        'Johnson City',
        'Nashville',
        'Sparta',
    ]),
    ('USA', 'CA', 'California', [
        'Corona',
        'Madera',
        'Temecula',
        'Garberville',
        'Chino',
        'Banning',
        'Merced',
    ]),
    ('USA', 'GA', 'Georgia', [
        'Union Point',
        'Social Circle',
        'Conyers',
        'Decatur',
    ]),
    ('USA', 'UT', 'Utah', [
        'Brigham City',
        'Layton',
        'Cedar City',
    ]),
    ('USA', 'NC', 'North Carolina', [
        'Latta',
        'Warsaw',
        'Statesville',
        'East Flat Rock',
        'Fort Mill',
    ]),
    ('USA', 'OH', 'Ohio', [
        'North Canton',
        'Hudson',
        'Streetsboro',
        'Holgate',
        'Batavia',
        'Ashland',
        'Elyria',
        'Austinburg',
    ]),
    ('USA', 'TX', 'Texas', [
        'Walburg',
        'Burnet',
        'Fort Worth',
        'Bryan',
        'La Porte',
        'Freeport',
        'Houston',
        'Center',
        'Pearland',
        'Glen Rose',
        'Midland',
        'Cypress',
    ]),
    ('USA', 'WI', 'Wisconsin', [
        'Port Washington',
        'Lake Mills',
        'Two Rivers',
        'Racine',
        'Beaver Dam',
        'Milwaukee',
        'Darien',
        'Sheboygan Falls',
    ]),
    ('USA', 'FL', 'Florida', [
        'Lutz',
        'Rockledge',
        'Winter Park',
        'Lake Wales',
    ]),
    ('USA', 'OK', 'Oklahoma', [
        'Sallisaw',
        'Ponca City',
        'Pocasset',
    ]),
    ('USA', 'AR', 'Arkansas', [
        'Gravette',
        'Rogers',
    ]),
    ('USA', 'MI', 'Michigan', [
        'Constantine',
        'Saginaw',
        'Madison Heights',
    ]),
    ('USA', 'PA', 'Pennsylvania', [
        'Lake City',
        'Strasburg',
        'Reading',
        'Leetsdale',
    ]),
    ('USA', 'OR', 'Oregon', [
        'Portland',
    ]),
    ('USA', 'ID', 'Idaho', [
        'Boise',
    ]),
    ('USA', 'MT', 'Montana', [
        'Bozeman',
        'Missoula',
    ]),
    ('USA', 'WY', 'Wyoming', [
        'Casper',
    ]),
    ('USA', 'SD', 'South Dakota', [
        'Olivet',
        'Tea',
    ]),
    ('USA', 'DE', 'Delaware', [
        'Frankford',
    ]),
    ('USA', 'NY', 'New York', [
        'Canastota',
        'Cortland',
    ]),
    ('USA', 'CO', 'Colorado', [
        'Durango',
    ]),
    ('USA', 'IL', 'Illinois', [
        'East Moline',
    ]),
    ('USA', 'MS', 'Mississippi', [
        'West Point',
    ]),
    ('USA', 'WA', 'Washington', [
        'Vancouver',
    ]),
    ('USA', 'AL', 'Alabama', [
        'Alexander City',
    ]),
    ('USA', 'MA', 'Massachusetts', [
        'Leominster',
    ]),
    ('USA', 'NH', 'New Hampshire', [
        'Gilford',
    ]),
    ('USA', 'NE', 'Nebraska', [
        'Sidney',
    ]),

    # --------------------------------------------------------
    # MEXICO
    # --------------------------------------------------------
    ('MEX', 'YU', 'Yucatan', [
        'Merida',
        'Tablaje Catastral',
    ]),
    ('MEX', 'QR', 'Queretaro', [
        'El Marques',
        'Santiago de Queretaro',
        'Almacen',
    ]),
    ('MEX', 'JA', 'Jalisco', [
        'Tlajomulco de Zuniga',
    ]),
    ('MEX', 'EM', 'Estado de Mexico', [
        'Naucalpan',
    ]),
    ('MEX', 'PU', 'Puebla', [
        'Puebla Momoxpan',
        'Cholula',
    ]),
    ('MEX', 'NZ', 'Nezahualcoyotl', [
        'Parque Industrial Izcalli',
    ]),
    ('MEX', 'VC', 'Veracruz', [
        'Ciudad Industrial Bruno Pagliai',
    ]),
    ('MEX', 'AG', 'Aguascalientes', [
        'Aguascalientes',
    ]),
    ('MEX', 'CM', 'Ciudad de Mexico', [
        'Coyoacan',
    ]),
    ('MEX', 'GU', 'Guanajuato', [
        'Celaya',
        'Ciudad de Leon',
    ]),
    ('MEX', 'NL', 'Nuevo Leon', [
        'General Escobedo',
    ]),
    ('MEX', 'BC', 'Baja California', [
        'Santos Ensenada',
    ]),

    # --------------------------------------------------------
    # AUSTRALIA
    # --------------------------------------------------------
    ('AUS', 'VI', 'Victoria', [
        'Swan Hill',
        'Seaford',
        'Pakenham',
        'Ballarat Carngham',
        'Irymple',
        'Melbourne',
        'Somerville',
        'Delacombe',
        'Campbellfield',
    ]),
    ('AUS', 'QL', 'Queensland', [
        'North Rockhampton',
        'Narangba',
        'Helidon Spa',
        'Yatala',
    ]),
    ('AUS', 'NS', 'New South Wales', [
        'Rutherford',
        'Silverwater',
        'Fountaindale',
        'Silverdale',
    ]),
    ('AUS', 'SA', 'South Australia', [
        'Lonsdale',
        'Edinburgh',
    ]),
    ('AUS', 'TA', 'Tasmania', [
        'Kings Meadows',
    ]),
    ('AUS', 'WA', 'Western Australia', [
        'Canning Vale',
    ]),

    # --------------------------------------------------------
    # CANADA
    # --------------------------------------------------------
    ('CAN', 'QC', 'Quebec', [
        'Drummondville',
        'Granby',
        'East Farnham',
    ]),
    ('CAN', 'AB', 'Alberta', [
        'Morinville',
        'Edmonton',
    ]),
    ('CAN', 'SK', 'Saskatchewan', [
        'Englefeld',
        'Saskatoon',
    ]),
    ('CAN', 'ON', 'Ontario', [
        'Stoney Creek',
        'Grassie',
        'Fort Erie',
        'Rodney',
    ]),
    ('CAN', 'MB', 'Manitoba', [
        'Winnipeg',
    ]),

    # --------------------------------------------------------
    # VENEZUELA
    # --------------------------------------------------------
    ('VEN', 'CA', 'Carabobo', [
        'Calle La Pedrera',
    ]),
    ('VEN', 'ZU', 'Zulia', [
        'Municipio Miranda',
    ]),
    ('VEN', 'AR', 'Aragua', [
        'Santa Cruz de Aragua',
    ]),
    ('VEN', 'BO', 'Bolivar', [
        'Puerto Ordaz',
    ]),

    # --------------------------------------------------------
    # CHILE
    # --------------------------------------------------------
    ('CHL', 'RM', 'Region Metropolitana', [
        'Colina',
        'Calera de Tango',
    ]),
    ('CHL', 'AT', 'Atacama', [
        'Lautaro',
    ]),

    # --------------------------------------------------------
    # COLOMBIA
    # --------------------------------------------------------
    ('COL', 'DC', 'Bogota', [
        'Bogota',
    ]),
    ('COL', 'CU', 'Cundinamarca', [
        'Soacha',
    ]),

    # --------------------------------------------------------
    # ECUADOR
    # --------------------------------------------------------
    ('ECU', 'GU', 'Guayas', [
        'Guayaquil',
        'Duran',
        'Via Duran Tambo',
    ]),
    ('ECU', 'TU', 'Tungurahua', [
        'Ambato',
    ]),
    ('ECU', 'CA', 'Cartorama', [
        'Cartorama',
    ]),

    # --------------------------------------------------------
    # ARGENTINA
    # --------------------------------------------------------
    ('ARG', 'SF', 'Santa Fe', [
        'Las Parejas',
    ]),
    ('ARG', 'BA', 'Buenos Aires', [
        'Buenos Aires',
    ]),
    ('ARG', 'SE', 'Santiago del Estero', [
        'La Banda',
    ]),

    # --------------------------------------------------------
    # PANAMA
    # --------------------------------------------------------
    ('PAN', 'PA', 'Panama', [
        'Ciudad de Panama',
        'Tocumen',
    ]),
    ('PAN', 'CO', 'Cocle', [
        'Aguadulce',
    ]),

    # --------------------------------------------------------
    # PARAGUAY
    # --------------------------------------------------------
    ('PRY', 'CE', 'Central', [
        'Luque',
    ]),

    # --------------------------------------------------------
    # PERU (no specific state/city)
    # --------------------------------------------------------

    # --------------------------------------------------------
    # COSTA RICA
    # --------------------------------------------------------
    ('CRI', 'SJ', 'San Jose', [
        'San Jose',
        'El Coyol de Alajuela',
    ]),

    # --------------------------------------------------------
    # NOVA ZELANDIA
    # --------------------------------------------------------
    ('NZL', 'AU', 'Auckland', [
        'Penrose',
        'Wiri',
    ]),
    ('NZL', 'BP', 'Bay of Plenty', [
        'Tauranga',
    ]),

    # --------------------------------------------------------
    # COREIA DO SUL
    # --------------------------------------------------------
    ('KOR', 'SE', 'Seoul', [
        'Dongjak-ku',
    ]),

    # --------------------------------------------------------
    # REINO UNIDO (Inglaterra)
    # --------------------------------------------------------
    ('GBR', 'SU', 'Suffolk', [
        'Halesworth',
    ]),
    ('GBR', 'NO', 'Nottinghamshire', [
        'Newark',
    ]),
    ('GBR', 'HA', 'Hampshire', [
        'Andover',
    ]),
    ('GBR', 'WY', 'West Yorkshire', [
        'Elland',
    ]),

    # --------------------------------------------------------
    # FRANCA
    # --------------------------------------------------------
    ('FRA', 'PI', 'Picardie', [
        'Friville Escarbotin',
    ]),
    ('FRA', 'BR', 'Bretagne', [
        'Dol de Bretagne',
        'Baguer Pican',
    ]),
    ('FRA', 'AI', 'Ain', [
        'Bellignat',
    ]),

    # --------------------------------------------------------
    # IRLANDA
    # --------------------------------------------------------
    ('IRL', 'GA', 'Galway', [
        'Tuam',
    ]),
    ('IRL', 'AM', 'Armagh', [
        'Portadown',
    ]),

    # --------------------------------------------------------
    # ALEMANHA
    # --------------------------------------------------------
    ('DEU', 'NW', 'Renania do Norte', [
        'Witten',
    ]),

    # --------------------------------------------------------
    # TAILANDIA
    # --------------------------------------------------------
    ('THA', 'NO', 'Nonthaburi', [
        'Bangraknoi',
    ]),
    ('THA', 'SP', 'Samutprakarn', [
        'Amphur Muang',
    ]),
    ('THA', 'BK', 'Bangkok', [
        'Rajthevee',
    ]),

    # --------------------------------------------------------
    # TRINIDAD E TOBAGO
    # --------------------------------------------------------
    ('TTO', 'SJ', 'San Juan', [
        'Barataria',
    ]),

    # --------------------------------------------------------
    # IRAN
    # --------------------------------------------------------
    ('IRN', 'MZ', 'Mazandaran', [
        'Khazarabad',
    ]),

    # --------------------------------------------------------
    # BELGICA
    # --------------------------------------------------------
    ('BEL', 'WV', 'West-Vlaanderen', [
        'Dadizele',
    ]),

    # --------------------------------------------------------
    # JAMAICA
    # --------------------------------------------------------
    ('JAM', 'KI', 'Kingston', [
        'Kingston',
    ]),

    # --------------------------------------------------------
    # MAURITIUS
    # --------------------------------------------------------
    ('MUS', 'MU', 'Mauritius', [
        'Rich Terre',
    ]),

    # --------------------------------------------------------
    # SRI LANKA (no specific state/city)
    # --------------------------------------------------------

    # --------------------------------------------------------
    # ISRAEL (no specific state/city)
    # --------------------------------------------------------

    # --------------------------------------------------------
    # BOLIVIA (no specific state/city)
    # --------------------------------------------------------

    # --------------------------------------------------------
    # HAITI (no specific state/city)
    # --------------------------------------------------------

    # --------------------------------------------------------
    # ARABIA SAUDITA (no specific state/city)
    # --------------------------------------------------------

    # --------------------------------------------------------
    # MALAYSIA
    # --------------------------------------------------------
    ('MYS', 'SL', 'Selangor', [
        'Selangor',
    ]),

    # --------------------------------------------------------
    # REPUBLICA DOMINICANA
    # --------------------------------------------------------
    ('DOM', 'SC', 'San Cristobal', [
        'Zona Industrial Haina',
    ]),

    # --------------------------------------------------------
    # AFRICA DO SUL
    # --------------------------------------------------------
    ('ZAF', 'GT', 'Gauteng', [
        'Rosslyn',
    ]),

    # --------------------------------------------------------
    # NOVA CALEDONIA
    # --------------------------------------------------------
    ('NCL', 'SU', 'Sud', [
        'Noumea',
    ]),
]


class Command(BaseCommand):
    help = 'Seed states and cities based on customer data'

    def handle(self, *args, **options):
        self.stdout.write('Starting state and city seed...')
        self.stdout.write('(Requirement: country seed already executed)\n')

        states_created = 0
        states_existing = 0
        cities_created = 0
        cities_existing = 0
        errors = []

        for country_acronym, state_acronym, state_name, cities in DATA:
            try:
                country = Country.objects.get(acronym=country_acronym)
            except Country.DoesNotExist:
                errors.append(f'Country not found: {country_acronym}')
                continue

            # Create state
            state, created = State.objects.get_or_create(
                acronym=state_acronym,
                country=country,
                defaults={'name': state_name},
            )

            if created:
                states_created += 1
                self.stdout.write(f'  [OK] State: {state_name} ({state_acronym}) - {country.name}')
            else:
                states_existing += 1

            # Create cities
            for city_name in cities:
                _, created = City.objects.get_or_create(
                    name=city_name,
                    state=state,
                )

                if created:
                    cities_created += 1
                    self.stdout.write(f'       + {city_name}')
                else:
                    cities_existing += 1

        # Summary
        self.stdout.write('\n--- Summary ---')
        self.stdout.write(f'  States created: {states_created}')
        self.stdout.write(f'  States already existing: {states_existing}')
        self.stdout.write(f'  Cities created: {cities_created}')
        self.stdout.write(f'  Cities already existing: {cities_existing}')
        self.stdout.write(f'  Total states: {State.objects.count()}')
        self.stdout.write(f'  Total cities: {City.objects.count()}')

        if errors:
            self.stdout.write('\n--- Errors ---')
            for error in errors:
                self.stderr.write(f'  [!] {error}')