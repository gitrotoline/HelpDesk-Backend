from django.contrib import admin

from .models import (
    TicketComment,
    TicketCommentAttachment,
    TicketLog,
    TicketPriority,
    TicketView,
    TicketStatus,
    Ticket,
    TicketAttachment,
    TicketRecipient,
    TicketType,
    TicketWatcher,
)


class TicketAttachmentInline(admin.TabularInline):
    model = TicketAttachment
    extra = 0


class TicketCommentAttachmentInline(admin.TabularInline):
    model = TicketCommentAttachment
    extra = 0


class TicketRecipientInline(admin.TabularInline):
    model = TicketRecipient
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'status', 'priority', 'type_of_ticket', 'sector_name', 'user_id', 'created_at', 'closed_at')
    list_filter = ('status', 'priority', 'type_of_ticket', 'created_at')
    search_fields = ('subject', 'description')
    readonly_fields = ('user_id', 'created_at', 'updated_at', 'closed_at')
    filter_horizontal = ('mentions',)
    inlines = [TicketRecipientInline, TicketAttachmentInline]


@admin.register(TicketStatus)
class TicketStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_default', 'is_final')


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(TicketPriority)
class TicketPriorityAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'user_name', 'body_short', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('body',)
    readonly_fields = ('user_id', 'created_at', 'updated_at')
    inlines = [TicketCommentAttachmentInline]

    @admin.display(description='Comentário')
    def body_short(self, obj):
        return obj.body[:60] + ('…' if len(obj.body) > 60 else '')


@admin.register(TicketLog)
class TicketLogAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'user_id', 'action', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('action',)

    # Log é trilha de auditoria: só leitura no admin.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TicketView)
class TicketViewAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'user_id', 'viewed_at')
    list_filter = ('viewed_at',)


@admin.register(TicketWatcher)
class TicketWatcherAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'kind', 'target_name', 'origin', 'created_at')
    list_filter = ('kind', 'origin')
    search_fields = ('target_name',)
    readonly_fields = ('created_at',)
