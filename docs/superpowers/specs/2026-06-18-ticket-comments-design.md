# Design — Comentários/respostas em tickets com anexos

Data: 2026-06-18
App: `tickets` (backend Django + DRF)

## Objetivo

Permitir que pessoas respondam a um ticket através de uma **thread de comentários**.
Qualquer usuário com acesso ao ticket pode comentar, e cada comentário pode levar
**anexos** (somente URL, igual ao padrão atual de `TicketAttachment`). Cada ação
sobre um comentário (criar/editar/excluir) registra um `TicketLog` para auditoria,
e o disparo de notificações avisa os interessados no ticket.

Sem conceito de "atendente designado" nem entidade própria de atendente — qualquer
usuário autorizado que comenta é, na prática, quem está respondendo.

## Decisões já tomadas

- **Escopo**: somente comentários/respostas (thread). Sem assignee/atendente.
- **Anexos**: somente URL (o front faz upload no storage externo e envia a URL),
  mesmo padrão do `TicketAttachment` existente.
- **Modelagem**: modelos separados — `TicketComment` + `TicketCommentAttachment`
  (cada tabela com um propósito claro; cascade próprio).
- **Notificações ao comentar**: dono do ticket + recipients (cópia) + setor.
  Não notificar quem já comentou. Não notificar o próprio autor.
- **Permissões**: quem vê o ticket pode comentar (mesmo escopo do `TicketViewSet`).
  O autor edita/exclui os próprios comentários; admin (`tier_admin`) exclui qualquer.
- **Auditoria**: cada ação de comentário gera um `TicketLog`.

## Fora de escopo (YAGNI)

- Comentar não muda o status do ticket.
- Sem upload binário no Django (continua só URL).
- Sem "notificar quem já comentou na thread".
- Sem entidade de atendente / assignee.

## 1. Modelos (`tickets/models.py`)

```python
class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    user_id = models.UUIDField()                 # autor (RemoteUser do auth-server)
    user_name = models.CharField(max_length=150, blank=True, default='')  # snapshot do nome
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'db_ticket_comment'
        verbose_name = 'Ticket Comment'
        verbose_name_plural = 'Ticket Comments'
        ordering = ['created_at']                 # thread em ordem cronológica

    def __str__(self):
        return f'#{self.ticket_id} - {self.user_name}'


class TicketCommentAttachment(models.Model):
    comment = models.ForeignKey(TicketComment, on_delete=models.CASCADE, related_name='attachments')
    url = models.URLField(max_length=500)
    name = models.CharField(max_length=255, blank=True, default='')  # nome amigável p/ exibir
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_comment_attachment'
        verbose_name = 'Ticket Comment Attachment'
        verbose_name_plural = 'Ticket Comment Attachments'

    def __str__(self):
        return self.url
```

Segue o padrão existente: `user_id` UUID + snapshot do nome (sem FK para usuário
local — usuários vêm do auth-server via JWT), `db_table` no padrão `db_*`, anexo
guardando só `url`.

## 2. Serializers (`tickets/serializer.py`)

### `TicketCommentAttachmentSerializer`
- `fields = ["id", "url", "name", "uploaded_at"]`
- `read_only_fields = ["uploaded_at"]`

### `TicketCommentSerializer`
- **Leitura**: `id, ticket, user_id, user_name, body, created_at, updated_at, attachments`
  (`attachments` aninhado via `TicketCommentAttachmentSerializer(many=True, read_only=True)`).
- **Escrita**: `body`, `ticket`, e `attachments_input` (lista de `{url, name}`,
  `write_only`, `required=False`) — mesmo estilo do `recipients` no `TicketSerializer`.
- `read_only_fields = ["user_id", "user_name", "created_at", "updated_at"]`.
- Helper `_sync_attachments(comment, items)`: limpa e recria os anexos
  (idempotente — mesmo espírito do `_sync_recipients`).
- `create(validated_data)`: extrai `attachments_input`, cria o comentário,
  `bulk_create` dos anexos.
- `update(instance, validated_data)`: edita `body`; se `attachments_input` veio,
  re-sincroniza os anexos. `ticket` não muda no update.

## 3. Escopo de visibilidade compartilhado

A regra "quais tickets este usuário pode ver" hoje vive em
`TicketViewSet.get_queryset`. Vamos **extrair** essa regra para um helper
reutilizável (ex.: função `ticket_visibility_q(user, prefix='')` em
`tickets/filter.py` ou um novo `tickets/scope.py`), que devolve o `Q` de
visibilidade:

- `user` admin (`has_perm('user.tier_admin')`) → sem filtro (todos).
- senão: `Q(user_id=user.id) | Q(recipients__user_id=user.id)` e, se o usuário
  tem setor, `| Q(sector_id=user.sector.id)`.

O `prefix` permite aplicar a mesma regra a partir de outro modelo
(ex.: `comments` filtram por `ticket__user_id=...` usando `prefix='ticket__'`).

- `TicketViewSet.get_queryset` passa a usar o helper (sem mudança de comportamento).
- `TicketCommentViewSet.get_queryset` usa o helper com `prefix='ticket__'`.

## 4. View (`tickets/views.py`) — `TicketCommentViewSet(ModelViewSet)`

- `queryset = TicketComment.objects.prefetch_related('attachments')`.
- `serializer_class = TicketCommentSerializer`.
- `filterset_fields = ['ticket']` → front lista a thread com
  `GET /tickets/comments/?ticket=<id>`.
- `ordering = ['created_at']`.
- `get_queryset`: aplica `ticket_visibility_q(user, prefix='ticket__')` →
  o usuário só vê comentários de tickets que ele pode ver.
- `perform_create(serializer)`:
  - `comment = serializer.save(user_id=request.user.id, user_name=request.user.get_full_name())`.
  - `TicketLog.objects.create(ticket=comment.ticket, user_id=..., user_name=..., action='Comentário adicionado')`.
  - Notifica dono + recipients + setor (excluindo o próprio autor):
    - `notify([owner_id] + recipient_ids, 'ticket', ticket.pk, 'Nova resposta no ticket #<id>', request.user)`
      (filtra para remover o próprio autor da lista).
    - `notify_sector(ticket.sector_id, 'ticket', ticket.pk, 'Nova resposta no ticket #<id>', request.user, request.user.auth_header)`.
- `perform_update(serializer)`:
  - Salva, e `TicketLog ... action='Comentário editado'`.
- `perform_destroy(instance)`:
  - Captura `ticket`/dados antes do delete; `instance.delete()`;
    `TicketLog ... action='Comentário excluído'`.

### Permissão de objeto (editar/excluir)

Método `check_object_permissions`/auxiliar aplicado em `update`/`partial_update`/`destroy`:

- **Editar** (`update`/`partial_update`): só o autor (`comment.user_id == request.user.id`),
  senão `403`.
- **Excluir** (`destroy`): o autor **ou** admin (`has_perm('user.tier_admin')`),
  senão `403`.
- Criar/listar/ver: liberado dentro do escopo de visibilidade (já filtrado).

## 5. Rota (`tickets/urls.py`)

```python
router.register("comments", TicketCommentViewSet, basename="ticket-comment")
# ANTES de router.register("", TicketViewSet, ...) — senão /comments/ é
# capturado como id de ticket pela rota de detalhe (mesmo motivo já comentado).
```

## 6. Admin (`tickets/admin.py`)

- `TicketCommentAttachmentInline(admin.TabularInline)` → `model = TicketCommentAttachment`.
- `@admin.register(TicketComment) class TicketCommentAdmin`:
  - `list_display = ('id', 'ticket', 'user_name', 'body_short', 'created_at')`
    (`body_short` = trecho do corpo).
  - `list_filter = ('created_at',)`, `search_fields = ('body',)`,
    `readonly_fields = ('user_id', 'created_at', 'updated_at')`.
  - `inlines = [TicketCommentAttachmentInline]`.

## 7. Migration

Uma migration nova em `tickets/migrations/` criando `TicketComment` e
`TicketCommentAttachment` (gerada por `makemigrations`).

## 8. Testes (`tickets/tests.py`)

1. Criar comentário sem anexos → 201, `TicketLog 'Comentário adicionado'` criado.
2. Criar comentário com anexos → anexos persistidos e retornados aninhados.
3. Listar `?ticket=<id>` → só comentários daquele ticket, em ordem cronológica.
4. Escopo: usuário sem acesso ao ticket não vê os comentários e não consegue criar.
5. Autor edita o próprio comentário → 200 + `TicketLog 'Comentário editado'`.
6. Não-autor tenta editar/excluir → 403.
7. Admin exclui comentário de outro → 204 + `TicketLog 'Comentário excluído'`.
8. Notificações: ao comentar, dono + recipients + setor recebem; autor não recebe.
