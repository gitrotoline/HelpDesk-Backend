from django.contrib import admin

from .models import (
    Machine,
    MachineArm,
    MachineCar,
    MachineLanguage,
    MachineModel,
    MachineModelSize,
    MachineOptional,
    MachineSize,
    MachineVoltage,
)


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'enterprise', 'status', 'sap_order', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('serial_number', 'sap_order')


@admin.register(MachineModelSize)
class MachineModelSizeAdmin(admin.ModelAdmin):
    list_display = ('model', 'size', 'sap_code')
    search_fields = ('sap_code', 'model__name', 'size__name')


@admin.register(MachineOptional)
class MachineOptionalAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


# Lookups simples (nome só) — registro padrão.
@admin.register(MachineModel)
class MachineModelAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(MachineVoltage)
class MachineVoltageAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(MachineLanguage)
class MachineLanguageAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(MachineArm)
class MachineArmAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(MachineCar)
class MachineCarAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(MachineSize)
class MachineSizeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
