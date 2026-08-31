from sector.services import list_sector_user_ids

from .models import Notification


def notify(recipient_ids, category, target_id, message, actor):
    """Cria 1 notificação por destinatário (sem duplicar). `actor` é quem disparou
    a ação (RemoteUser do auth-server); guardamos id/nome só para exibição.

    Ninguém é notificado da própria ação. A regra fica aqui, e não em cada
    chamador, porque só o `perform_create` de comentário filtrava o autor — os
    outros caminhos (fechar, reabrir, e o fan-out de setor) notificavam quem
    tinha acabado de agir.
    """
    actor_id = str(actor.id) if actor is not None else None
    recipients = {str(uid) for uid in recipient_ids if uid} - {actor_id}
    Notification.objects.bulk_create(
        Notification(
            recipient_id=uid,
            actor_id=actor.id,
            actor_name=actor.get_full_name(),
            category=category,
            target_id=str(target_id),
            message=message,
        )
        for uid in recipients
    )


def notify_sector(sector_id, category, target_id, message, actor, auth_header):
    """Fan-out best-effort: resolve os membros do setor no auth-server (repassa o
    token do usuário) e notifica cada um. Em erro de rede não notifica ninguém,
    sem quebrar a ação que disparou."""
    if not sector_id:
        return
    member_ids = list_sector_user_ids(sector_id, auth_header)
    notify(member_ids, category, target_id, message, actor)
