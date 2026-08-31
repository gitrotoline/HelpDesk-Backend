from django.db.models import Q

from .models import TicketWatcher


def ticket_visibility_q(user, prefix=''):
    """`Q` que filtra os tickets visíveis para `user` — usado pelo TicketViewSet e,
    com prefix='ticket__', pelo TicketCommentViewSet (filtra comentários pelo ticket).

    Admin (tier_admin) enxerga tudo: devolve um Q vazio (sem filtro). Caso contrário,
    o usuário vê os tickets que abriu, em que está em cópia ou do seu setor.
    `prefix` permite aplicar a regra a partir de outro modelo (ex.: 'ticket__').
    """
    if user.has_perm('user.tier_admin'):
        return Q()

    def field(name):
        return f'{prefix}{name}'

    scope = Q(**{field('user_id'): user.id}) | Q(**{field('recipients__user_id'): user.id})
    # setor vem do JWT (RemoteUser.sector); pode ser None se o usuário não tem.
    if user.sector and user.sector.id:
        scope |= Q(**{field('sector_id'): user.sector.id})
        # Acompanhantes: só as linhas de setor concedem acesso. A linha de
        # departamento é registro de origem — o token traz setor, não
        # departamento, então ela nunca casaria com ninguém.
        scope |= Q(**{field('watchers__kind'): TicketWatcher.KIND_SECTOR,
                      field('watchers__target_id'): user.sector.id})
    return scope
