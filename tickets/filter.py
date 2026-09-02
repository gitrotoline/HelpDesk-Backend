import django_filters
from django.db.models import F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest

from .models import Ticket, TicketComment, TicketView


class TicketFilter(django_filters.FilterSet):
    priority_highlight = django_filters.BooleanFilter(
        field_name="priority__highlight",
        help_text="Filtra chamados cuja prioridade está marcada para destaque na listagem.",
    )
    is_open = django_filters.BooleanFilter(
        method="filter_is_open",
        help_text="Filtra chamados em aberto (closed_at nulo) quando true, ou fechados quando false.",
    )
    # HD-31 (dashboard): "ninguém pegou" é a situação com is_default, não o
    # nome "Aberto" — renomear no cadastro não quebra a home. Os dois valores
    # excluem fechados de propósito: os blocos que usam isto são "em aberto"
    # por definição, e exigir is_open junto viraria redundância em todo link.
    awaiting = django_filters.BooleanFilter(
        method="filter_awaiting",
        help_text="true: em aberto e na situação padrão (ninguém pegou). "
                  "false: em aberto e fora da situação padrão (em andamento, "
                  "espera de material...).",
    )

    # HD-31 (dashboard): "tem novidade" = em aberto E (nunca abri OU a última
    # atividade é posterior à minha última abertura). Atividade = updated_at
    # do chamado ou comentário DE OUTRA PESSOA. Comentário meu não conta:
    # não é novidade para mim, e o refresh da tela depois da minha ação já
    # avança meu viewed_at (retrieve) para o resto.
    has_news = django_filters.BooleanFilter(
        method="filter_has_news",
        help_text="true: houve atividade (comentário de outra pessoa ou "
                  "alteração) depois da última vez que o usuário abriu o "
                  "chamado, ou ele nunca abriu. Só chamados em aberto.",
    )

    class Meta:
        model = Ticket
        fields = {
            "status": ["exact"],
            "priority": ["exact"],
            "type_of_ticket": ["exact"],
            "user_id": ["exact"],
            "sector_id": ["exact"],
            "created_at": ["date", "gte", "lte"],
        }

    def filter_is_open(self, queryset, name, value):
        if value:
            return queryset.filter(closed_at__isnull=True)
        return queryset.filter(closed_at__isnull=False)

    def filter_awaiting(self, queryset, name, value):
        open_qs = queryset.filter(closed_at__isnull=True)
        if value:
            return open_qs.filter(status__is_default=True)
        return open_qs.exclude(status__is_default=True)

    def filter_has_news(self, queryset, name, value):
        user_id = self.request.user.id
        last_other_comment = (
            TicketComment.objects
            .filter(ticket=OuterRef('pk'))
            .exclude(user_id=user_id)
            .order_by('-created_at')
            .values('created_at')[:1]
        )
        my_view = (
            TicketView.objects
            .filter(ticket=OuterRef('pk'), user_id=user_id)
            .values('viewed_at')[:1]
        )
        # Coalesce antes do Greatest: sem comentário de outro, a subquery é
        # NULL. Postgres ignora NULL no Greatest, mas deixar explícito não
        # depende disso.
        annotated = queryset.annotate(
            last_activity=Greatest(
                F('updated_at'),
                Coalesce(Subquery(last_other_comment), F('updated_at')),
            ),
            my_viewed_at=Subquery(my_view),
        )
        news = annotated.filter(closed_at__isnull=True).filter(
            Q(my_viewed_at__isnull=True) | Q(last_activity__gt=F('my_viewed_at'))
        )
        if value:
            return news
        return queryset.exclude(pk__in=news.values('pk'))
