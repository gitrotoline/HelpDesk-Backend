# Design — Dashboard da home (backend)

Data: 2026-09-01
App: `backend` (Django 5 + DRF, app `tickets`)
Par no frontend: `frontend/docs/superpowers/specs/2026-09-01-dashboard-home-frontend-design.md`
Jira: HD-31

## Objetivo

Dar à home do frontend o que ela precisa para mostrar, por usuário, **o que é
dele para agir**: chamados aguardando o setor dele, em andamento no setor dele,
abertos por ele, e com novidade que ele ainda não viu.

Tudo isso é **filtro sobre a listagem que já existe** (`GET /tickets/`), que já
aplica o escopo de visibilidade (`ticket_visibility_q`) e já aceita `sector_id`,
`user_id`, `is_open` e `ordering`. O backend ganha só o que **não existe**:

1. o carimbo de visualização passa a ser "última vez que abri", não "primeira";
2. filtro `has_news` — houve atividade depois da minha última abertura;
3. filtro `awaiting` — está (ou não) na situação padrão, em aberto.

Nenhuma migration. Nenhum endpoint novo.

## Decisões tomadas

- **Sem endpoint agregado** (`/tickets/dashboard/`). Ele duplicaria no backend a
  lógica de listar que o `TicketFilter` já faz e testa, e criaria uma segunda
  fonte de verdade para "o que é aguardando". O front faz quatro chamadas em
  paralelo; nesta escala isso custa nada.
- **"Aguardando" é a situação com `is_default`**, não o nome "Aberto". Renomear
  a situação no cadastro não quebra a home.
- **"Espera de Material" conta como em andamento** (`awaiting=false`): é a única
  situação que não é padrão, nem `is_in_progress`, nem final, e o setor está com
  o chamado mesmo travado. Se isso incomodar no uso, a saída é uma flag nova no
  cadastro de situação — não um caso especial por nome.
- **Minha própria ação não é novidade para mim.** Dois mecanismos, sem tratar
  caso a caso: (a) comentário meu é excluído do cálculo de `last_activity`;
  (b) toda ação minha na tela recarrega o chamado (`retrieve`), que agora avança
  o meu `viewed_at` — então edição/mudança de situação feita por mim fica
  coberta pelo próprio fluxo da tela.
- **Novidade só em chamado aberto.** Fechado não pede ação; comentário num
  chamado fechado não o traz de volta para a home.
- **O `/tickets/stats/` existente não é usado** — e fica anotado como dívida
  (ver abaixo).

## Fora de escopo (YAGNI)

- Endpoint agregado / cache por usuário.
- Contagem de novidades no sino ou no menu.
- "Marcar como visto" sem abrir o chamado.
- Corrigir ou remover o `/tickets/stats/` (dívida separada).

## Mudança 1 — `retrieve` avança o `viewed_at`

Hoje (`TicketViewSet.retrieve`):

```python
TicketView.objects.get_or_create(ticket=instance, user_id=request.user.id)
```

`BaseView.viewed_at` é `auto_now_add`, então o carimbo fica na **primeira**
abertura para sempre. Passa a:

```python
TicketView.objects.update_or_create(
    ticket=instance, user_id=request.user.id,
    defaults={'viewed_at': timezone.now()},
)
```

`auto_now_add` só age no INSERT; no UPDATE o valor explícito em `defaults`
prevalece. Sem migration: o campo não muda, só quem escreve nele.

`NotificationView` herda o mesmo `BaseView` e **não muda** — a semântica de
"primeira vez" continua válida lá.

## Mudança 2 — filtro `has_news`

Em `tickets/filter.py`, no `TicketFilter`:

```python
has_news = django_filters.BooleanFilter(
    method='filter_has_news',
    help_text='true: houve atividade (comentário de outra pessoa ou alteração) '
              'depois da última vez que o usuário abriu o chamado, ou ele nunca '
              'abriu. Só chamados em aberto.',
)
```

Implementação (o `FilterSet` tem `self.request.user`):

```python
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
    qs = queryset.annotate(
        last_activity=Greatest(
            F('updated_at'),
            Coalesce(Subquery(last_other_comment), F('updated_at')),
        ),
        my_viewed_at=Subquery(my_view),
    )
    news = qs.filter(closed_at__isnull=True).filter(
        Q(my_viewed_at__isnull=True) | Q(last_activity__gt=F('my_viewed_at'))
    )
    if value:
        return news
    return queryset.exclude(pk__in=news.values('pk'))
```

Notas:
- `Coalesce` antes do `Greatest`: chamado sem comentário de outra pessoa tem
  a subquery NULL. Postgres (testes e produção — `ENGINE` em `settings.py`)
  ignora NULL no `Greatest`, mas o `Coalesce` deixa a intenção explícita e
  o comportamento igual se algum dia rodar noutro banco.
- `has_news=false` existe por simetria do `BooleanFilter`, mas a home não usa.
- `user_id` do comentário é `UUIDField`; `request.user.id` é `str` do JWT.
  O ORM converte na comparação — mesma situação já validada em
  `TicketView.objects.filter(user_id=user_id)` do `get_queryset`.

## Mudança 3 — filtro `awaiting`

```python
awaiting = django_filters.BooleanFilter(
    method='filter_awaiting',
    help_text='true: em aberto e na situação padrão (ninguém pegou). '
              'false: em aberto e fora da situação padrão (em andamento, '
              'espera de material...).',
)

def filter_awaiting(self, queryset, name, value):
    open_qs = queryset.filter(closed_at__isnull=True)
    if value:
        return open_qs.filter(status__is_default=True)
    return open_qs.exclude(status__is_default=True)
```

Os dois valores excluem fechados. Isso é de propósito: os dois blocos da home
que usam este filtro são "em aberto" por definição, e `is_open` viraria
redundante em todo link.

## Como a home combina (referência para o front)

| Bloco                           | Query                                  |
|---------------------------------|----------------------------------------|
| Aguardando meu setor            | `sector_id=<meu>&awaiting=true`        |
| Em andamento no meu setor       | `sector_id=<meu>&awaiting=false`       |
| Abertos por mim                 | `user_id=<eu>&is_open=true`            |
| Com novidade                    | `has_news=true`                        |

"Com novidade" usa só `has_news=true`: o escopo de visibilidade já limita ao
que me toca (meus, do meu setor, em cópia, acompanhando). Restringir a
estritamente "meus ou do meu setor" exigiria duas chamadas; a primeira versão
não faz isso.

Ordenação: `ordering=-priority__level,created_at` (urgente primeiro, depois o
mais antigo). Já suportado.

## Testes (`tickets/tests.py`, mesmo estilo de `TicketFilterHighlightAndOpenTests`)

`TicketViewTouchTests`
- abrir o chamado duas vezes → `viewed_at` da segunda é maior que o da primeira;
- continua um único registro por (chamado, usuário).

`TicketFilterHasNewsTests`
- nunca abri → aparece;
- abri e ninguém mexeu → não aparece;
- abri, outra pessoa comentou depois → aparece;
- abri, **eu** comentei depois → não aparece;
- abri, o chamado foi editado depois (`updated_at` avança) → aparece;
- chamado fechado com comentário novo de outro → não aparece;
- chamado fora do meu escopo com novidade → não aparece (prova que o filtro
  parte do `get_queryset` filtrado, não de `Ticket.objects.all()`).

`TicketFilterAwaitingTests`
- `awaiting=true` traz só padrão + aberto;
- `awaiting=false` traz aberto fora da padrão (inclui uma situação neutra tipo
  "Espera de Material");
- os dois excluem fechado, mesmo que o fechado esteja na situação padrão (dados
  ruins não vazam para a home).

Mutation check antes de dar por pronto: reverter o `update_or_create` para
`get_or_create` e confirmar que `TicketViewTouchTests` falha; trocar o
`.exclude(user_id=user_id)` por `.filter()` e confirmar que "eu comentei" falha.

## Dívida anotada (fora deste trabalho)

`GET /tickets/stats/` conta sobre `Ticket.objects.all()` — **sem** o escopo de
visibilidade — e guarda o resultado num cache único de 5 minutos para todos os
usuários. Qualquer autenticado vê totais por setor de chamados que não poderia
ver, e o número fica velho por até 5 minutos. Ninguém consome esse endpoint no
front hoje. Decidir entre remover ou refazer com escopo por usuário fica para um
item próprio.
