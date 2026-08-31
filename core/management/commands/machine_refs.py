from django.core.management.base import BaseCommand
from machines.models import (
    MachineArm,
    MachineCar,
    MachineLanguage,
    MachineModel,
    MachineSize,
    MachineVoltage,
)


SIZES = [
    "1.00",
    "2.00",
    "3.00",
    "4.00",
    "5.00",
    "6.00",
]

MODELS = [
    ("Carrossel", "CR"),
    ("Shuttle", "DC"),
    ("Lab", "LAB"),
    ("Open Flame", "OF"),
    ("Rock and Roll", "RAR"),
    ("Sphere Over", "SO"),
    ("TNC", "TNC"),
]

LINGUAGE = [
    "Português",
    "Inglês",
    "Espanhol"
]

VOLTAGE = [
    "220V",
    "380V",
]

CAR = [
    "1",
    "2",
    "3",
    "4",
    "5",
]

ARM = [
    "Braço Central",
    "Braço Offset C",
    "Braço Offset L"
]

class Command(BaseCommand):
    help = 'Seed the database with machine reference data (sizes and models)'

    def handle(self, *args, **options):
        self.stdout.write('Starting machine refs seed...')

        sizes_created = 0
        models_created = 0
        languages_created = 0
        voltages_created = 0
        cars_created = 0
        arms_created = 0

        for size_name in SIZES:
            _, was_created = MachineSize.objects.get_or_create(name=size_name)
            if was_created:
                sizes_created += 1
                self.stdout.write(f'  [OK] Size: {size_name}')

        for model_name, acronym in MODELS:
            _, was_created = MachineModel.objects.get_or_create(
                name=model_name,
                defaults={'acronym': acronym},
            )
            if was_created:
                models_created += 1
                self.stdout.write(f'  [OK] Model: {model_name} ({acronym})')

        for language_name in LINGUAGE:
            _, was_created = MachineLanguage.objects.get_or_create(name=language_name)
            if was_created:
                languages_created += 1
                self.stdout.write(f'  [OK] Language: {language_name}')

        for voltage_name in VOLTAGE:
            _, was_created = MachineVoltage.objects.get_or_create(name=voltage_name)
            if was_created:
                voltages_created += 1
                self.stdout.write(f'  [OK] Voltage: {voltage_name}')

        for car_name in CAR:
            _, was_created = MachineCar.objects.get_or_create(name=car_name)
            if was_created:
                cars_created += 1
                self.stdout.write(f'  [OK] Car: {car_name}')

        for arm_name in ARM:
            _, was_created = MachineArm.objects.get_or_create(name=arm_name)
            if was_created:
                arms_created += 1
                self.stdout.write(f'  [OK] Arm: {arm_name}')

        self.stdout.write('')
        self.stdout.write('Machine refs seed completed!')
        self.stdout.write(f'  Sizes created: {sizes_created}')
        self.stdout.write(f'  Models created: {models_created}')
        self.stdout.write(f'  Languages created: {languages_created}')
        self.stdout.write(f'  Voltages created: {voltages_created}')
        self.stdout.write(f'  Cars created: {cars_created}')
        self.stdout.write(f'  Arms created: {arms_created}')
        self.stdout.write(f'  Size total: {MachineSize.objects.count()}')
        self.stdout.write(f'  Model total: {MachineModel.objects.count()}')
        self.stdout.write(f'  Language total: {MachineLanguage.objects.count()}')
        self.stdout.write(f'  Voltage total: {MachineVoltage.objects.count()}')
        self.stdout.write(f'  Car total: {MachineCar.objects.count()}')
        self.stdout.write(f'  Arm total: {MachineArm.objects.count()}')
