# Chamados relacionados — Plano de implementação (backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor, só no detalhe do chamado, o resumo dos chamados relacionados nas duas direções (`mentions_detail` e `mentioned_in_detail`), filtrado pela visibilidade do usuário.

**Architecture:** Um serializer de resumo (`TicketRelatedSerializer`) e um serializer de detalhe (`TicketDetailSerializer`) que estende o `TicketSerializer` com dois `SerializerMethodField`. Cada campo aplica `ticket_visibility_q(request.user)` sobre a relação antes de serializar. O `TicketViewSet` usa o serializer de detalhe apenas na action `retrieve`, para a listagem não pagar 2 queries por linha.

**Tech Stack:** Django + DRF, `django_filters`, testes com `APITestCase` e `force_authenticate` com `RemoteUser` (auth via JWT do auth-server, sem User local).

**Spec:** `docs/superpowers/specs/2026-08-31-chamados-relacionados-backend-design.md`
**Par no frontend:** `frontend/docs/superpowers/specs/2026-08-31-chamados-relacionados-frontend-design.md`

## Global Constraints

- Ticket do Jira: **HD-31**. Toda mensagem de commit começa com `HD-31 `.
- Nenhuma dependência nova.
- O campo `mentions` (lista de pks) **não muda** — é o campo de escrita do formulário do frontend.
- Nenhuma migration: não há mudança de modelo.
- Rodar os testes com o banco de teste padrão: `python manage.py test tickets`.
- Comentários em português, no tom do arquivo (explicam o *porquê*, não o *o quê*).

---

### Task 1: Resumo do relacionado + direção direta (`mentions_detail`)

**Files:**
- Modify: `tickets/serializer.py` (imports no topo; classes novas no fim do arquivo)
- Modify: `tickets/views.py` (import + `get_serializer_class` no `TicketViewSet`, após `serializer_class` na linha ~107)
- Test: `tickets/tests.py` (classe nova no fim do arquivo)

**Interfaces:**
- Consumes: `ticket_visibility_q(user, prefix='')` de `tickets/scope.py`; `TicketSerializer` de `tickets/serializer.py`.
- Produces: `TicketRelatedSerializer`, `TicketDetailSerializer` (usados na Task 2); campo JSON `mentions_detail` no `GET /tickets/{id}/` (consumido pelo frontend).

- [ ] **Step 1: Escrever o teste que falha**

Adicionar no fim de `tickets/tests.py`:

```python
class RelatedTicketsTests(APITestCase):
    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='Principal', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.related = Ticket.objects.create(
            user_id=OWNER_ID, subject='Troca do toner', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.ticket.mentions.add(self.related)
        self.client.force_authenticate(user=make_user())

    def test_detail_returns_mentions_detail_with_subject_and_comments_count(self):
        TicketComment.objects.create(
            ticket=self.related, user_id=OWNER_ID, user_name='Test User', body='oi'
        )
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['mentions_detail']), 1)
        item = resp.data['mentions_detail'][0]
        self.assertEqual(item['id'], self.related.id)
        self.assertEqual(item['subject'], 'Troca do toner')
        self.assertEqual(item['status_name'], 'Aberto')
        self.assertEqual(item['comments_count'], 1)
        # O campo cru continua existindo — é o que o formulário grava.
        self.assertEqual(resp.data['mentions'], [self.related.id])
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `python manage.py test tickets.tests.RelatedTicketsTests -v 2`
Expected: FAIL com `KeyError: 'mentions_detail'`

- [ ] **Step 3: Implementar os serializers**

Em `tickets/serializer.py`, acrescentar aos imports do topo:

```python
from django.db.models import Count

from .scope import ticket_visibility_q
```

E no fim do arquivo:

```python
class TicketRelatedSerializer(serializers.ModelSerializer):
    """Resumo de um chamado relacionado — cabeçalho, sem descrição nem thread.
    As mensagens são buscadas sob demanda pelo front em /tickets/comments/."""
    status_name = serializers.CharField(source='status.name', read_only=True)
    priority_name = serializers.CharField(source='priority.name', read_only=True)
    comments_count = serializers.IntegerField(read_only=True)  # vem do annotate

    class Meta:
        model = Ticket
        fields = [
            'id', 'subject', 'status_name', 'priority_name',
            'user_name', 'sector_name', 'created_at', 'closed_at',
            'comments_count',
        ]


class TicketDetailSerializer(TicketSerializer):
    """TicketSerializer + os relacionados. Usado só no retrieve (ver views.py):
    os dois campos custam 2 queries por objeto, o que na listagem seria N+1."""
    mentions_detail = serializers.SerializerMethodField()

    def _related(self, manager):
        # Filtra pela MESMA regra de visibilidade dos chamados: sem isso, a
        # menção viraria uma porta lateral para ler chamado de outro setor.
        user = self.context['request'].user
        qs = (
            manager.filter(ticket_visibility_q(user))
            .select_related('status', 'priority')
            .annotate(comments_count=Count('comments', distinct=True))
            .distinct()  # o Q de visibilidade faz JOIN com recipients e repete linhas
            .order_by('-created_at')
        )
        return TicketRelatedSerializer(qs, many=True).data

    def get_mentions_detail(self, obj):
        return self._related(obj.mentions)
```

Em `tickets/views.py`, incluir `TicketDetailSerializer` no import de `.serializer` e acrescentar no `TicketViewSet`, logo abaixo de `serializer_class = TicketSerializer`:

```python
    def get_serializer_class(self):
        # Só o detalhe traz os relacionados; na listagem isso seria N+1.
        # close/reopen respondem com self.action = 'close'/'reopen' e seguem
        # usando o serializer normal — o front dá refresh depois de qualquer forma.
        if self.action == 'retrieve':
            return TicketDetailSerializer
        return self.serializer_class
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `python manage.py test tickets.tests.RelatedTicketsTests -v 2`
Expected: PASS (1 teste)

- [ ] **Step 5: Rodar a suíte inteira do app**

Run: `python manage.py test tickets`
Expected: OK, sem regressão nos testes de anexos/comentários existentes.

- [ ] **Step 6: Commit**

```bash
git add tickets/serializer.py tickets/views.py tickets/tests.py
git commit -m "HD-31 Ticket - Resumo dos chamados mencionados no detalhe"
```

---

### Task 2: Direção inversa + garantias de escopo

**Files:**
- Modify: `tickets/serializer.py` (`TicketDetailSerializer`)
- Test: `tickets/tests.py` (`RelatedTicketsTests`)

**Interfaces:**
- Consumes: `TicketDetailSerializer._related` (Task 1).
- Produces: campo JSON `mentioned_in_detail` no `GET /tickets/{id}/`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `RelatedTicketsTests`:

```python
    def test_detail_returns_mentioned_in_detail(self):
        # Direção inversa: outro chamado menciona este. A M2M é symmetrical=False,
        # então sem o campo novo essa relação é invisível na API.
        other = Ticket.objects.create(
            user_id=OWNER_ID, subject='Chamado que cita', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        other.mentions.add(self.ticket)
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertEqual(
            [i['id'] for i in resp.data['mentioned_in_detail']], [other.id]
        )

    def test_related_out_of_scope_is_hidden_but_pk_still_listed(self):
        # Chamado de outro usuário, sem setor e sem cópia: fora do escopo.
        secret = Ticket.objects.create(
            user_id=OTHER_ID, subject='Sigiloso', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.ticket.mentions.add(secret)
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        subjects = [i['subject'] for i in resp.data['mentions_detail']]
        self.assertNotIn('Sigiloso', subjects)          # assunto não vaza
        self.assertIn(secret.id, resp.data['mentions'])  # o pk continua (comportamento antigo)

    def test_admin_sees_related_out_of_scope(self):
        secret = Ticket.objects.create(
            user_id=OTHER_ID, subject='Sigiloso', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.ticket.mentions.add(secret)
        self.client.force_authenticate(
            user=make_user(user_id=OTHER_ID, permissions=['user.tier_admin'])
        )
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        subjects = [i['subject'] for i in resp.data['mentions_detail']]
        self.assertIn('Sigiloso', subjects)

    def test_list_does_not_include_related_fields(self):
        resp = self.client.get(reverse('ticket-list'))
        self.assertNotIn('mentions_detail', resp.data['results'][0])
        self.assertNotIn('mentioned_in_detail', resp.data['results'][0])
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python manage.py test tickets.tests.RelatedTicketsTests -v 2`
Expected: FAIL — `test_detail_returns_mentioned_in_detail` com `KeyError: 'mentioned_in_detail'`. (`test_related_out_of_scope_is_hidden_but_pk_still_listed`, `test_admin_sees_related_out_of_scope` e `test_list_does_not_include_related_fields` já devem passar com o código da Task 1 — eles existem para travar o comportamento contra regressão.)

- [ ] **Step 3: Implementar o campo da direção inversa**

Em `TicketDetailSerializer`, acrescentar o campo e o getter (o helper `_related` já serve os dois):

```python
    mentioned_in_detail = serializers.SerializerMethodField()
```

```python
    def get_mentioned_in_detail(self, obj):
        # related_name da M2M para self (ver Ticket.mentions no models.py).
        return self._related(obj.mentioned_in)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python manage.py test tickets.tests.RelatedTicketsTests -v 2`
Expected: PASS (5 testes)

- [ ] **Step 5: Rodar a suíte inteira do app**

Run: `python manage.py test tickets`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add tickets/serializer.py tickets/tests.py
git commit -m "HD-31 Ticket - Direcao inversa e escopo dos relacionados"
```

---

## Entrega para o frontend

Depois da Task 2, `GET /tickets/{id}/` devolve `mentions_detail` e
`mentioned_in_detail` no formato da seção 4 da spec. É o gatilho para começar o
plano do frontend (`frontend/docs/superpowers/plans/2026-08-31-chamados-relacionados.md`).
