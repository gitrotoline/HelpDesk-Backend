# Dashboard da home (backend) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer `GET /tickets/` responder às quatro perguntas da home (aguardando meu setor, em andamento no meu setor, abertos por mim, com novidade) só com filtros novos — sem endpoint novo, sem migration.

**Architecture:** Três mudanças no app `tickets`: (1) `retrieve` passa a avançar o `viewed_at` a cada abertura; (2) `TicketFilter` ganha `has_news` (atividade de outra pessoa depois da minha última abertura, ou nunca abri; só em aberto); (3) `TicketFilter` ganha `awaiting` (situação padrão vs. não-padrão, ambos em aberto). Tudo parte do `get_queryset` do `TicketViewSet`, que já aplica o escopo de visibilidade.

**Tech Stack:** Django 5, DRF, django-filter, Postgres (testes e produção). Spec: `docs/superpowers/specs/2026-09-01-dashboard-home-backend-design.md`.

## Global Constraints

- **Não commitar.** Decisão do usuário para esta rodada: todas as mudanças ficam no working tree. Onde um plano normalmente teria "Commit", aqui há "Verificar".
- Nenhuma migration: as três mudanças não tocam em campo de modelo. `python manage.py makemigrations --check --dry-run` tem que continuar dizendo "No changes detected".
- Todo teste segue o estilo dos existentes em `tickets/tests.py`: `APITestCase`, `self.client.force_authenticate(user=make_user(...))`, `reverse('ticket-list')` / `reverse('ticket-detail', args=[pk])`.
- Rodar os testes com o Python do venv: `./.venv/Scripts/python.exe manage.py test tickets` (na raiz do backend). Saída do console em ASCII quando for `print` seu — o terminal é cp1252.
- Chamado e comentário são criados direto no ORM nos testes (não via API), como nos testes vizinhos. Chamado precisa de `user_id`, `subject`, `type_of_ticket`, `priority`, `status`.
- `request.user.id` é `str`; `user_id` nos modelos é `UUIDField`. Compare via ORM (ele converte), nunca com `==` em Python.

---

## Estrutura de arquivos

- Modify: `tickets/views.py` — `TicketViewSet.retrieve` (linhas 160–164).
- Modify: `tickets/filter.py` — imports + dois filtros novos em `TicketFilter`.
- Modify: `tickets/tests.py` — três classes de teste novas no fim do arquivo.

Nada é criado. Helpers de teste que já existem e serão usados: `OWNER_ID`, `OTHER_ID`, `make_user(user_id=..., is_superuser=..., permissions=...)`, `make_user_with_sector(user_id, sector_id, sector_name=...)`.

---

### Task 1: `retrieve` avança o `viewed_at`

**Files:**
- Modify: `tickets/views.py:160-164`
- Test: `tickets/tests.py` (classe nova `TicketViewTouchTests`)

**Interfaces:**
- Consumes: `TicketView` (`tickets/models.py`, FK `ticket`, `user_id`, `viewed_at` herdado de `core.models.BaseView` com `auto_now_add=True`).
- Produces: nada novo em código; garante a semântica "`viewed_at` = última abertura" que a Task 2 assume.

- [ ] **Step 1: Escrever o teste que falha**

No fim de `tickets/tests.py`:

```python
class TicketViewTouchTests(APITestCase):
    """HD-31 (dashboard): abrir o chamado AVANÇA o viewed_at. Antes o registro
    era criado na primeira abertura e nunca mais tocado — servia para "já vi
    alguma vez", não para "vi por último quando", que é o que o filtro
    has_news precisa."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Baixa')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='Toque', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())
        self.url = reverse('ticket-detail', args=[self.ticket.pk])

    def test_second_open_moves_viewed_at_forward(self):
        self.client.get(self.url)
        first = TicketView.objects.get(ticket=self.ticket, user_id=OWNER_ID).viewed_at
        # Sem sleep: empurra o carimbo para o passado e abre de novo.
        TicketView.objects.filter(ticket=self.ticket, user_id=OWNER_ID).update(
            viewed_at=first - timezone.timedelta(minutes=5)
        )
        self.client.get(self.url)
        second = TicketView.objects.get(ticket=self.ticket, user_id=OWNER_ID).viewed_at
        self.assertGreater(second, first - timezone.timedelta(minutes=5))
        self.assertGreaterEqual(second, first)

    def test_still_one_row_per_ticket_and_user(self):
        self.client.get(self.url)
        self.client.get(self.url)
        self.assertEqual(
            TicketView.objects.filter(ticket=self.ticket, user_id=OWNER_ID).count(), 1
        )
```

`TicketView` já está no `from .models import (...)` do topo do arquivo? Confira com `grep -n "TicketView" tickets/tests.py | head -3`. Se não estiver, adicione ao bloco de import.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe manage.py test tickets.tests.TicketViewTouchTests -v 2`
Expected: `test_second_open_moves_viewed_at_forward` FAIL (`second` continua igual a `first - 5min`, porque `get_or_create` não toca o registro). `test_still_one_row...` PASS (já é assim hoje).

- [ ] **Step 3: Implementar**

Em `tickets/views.py`, substituir o `retrieve`:

```python
    def retrieve(self, request, *args, **kwargs):
        # Abrir o ticket registra a visualização do usuário (idempotente).
        # HD-31 (dashboard): AVANÇA o carimbo a cada abertura. O filtro
        # `has_news` compara a última atividade do chamado com este viewed_at;
        # com get_or_create ele ficava preso na primeira abertura e "novidade"
        # seria tudo que aconteceu desde sempre.
        instance = self.get_object()
        TicketView.objects.update_or_create(
            ticket=instance, user_id=request.user.id,
            defaults={'viewed_at': timezone.now()},
        )
        return Response(self.get_serializer(instance).data)
```

`timezone` já é importado no topo de `views.py` (`from django.utils import timezone`).

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe manage.py test tickets.tests.TicketViewTouchTests -v 2`
Expected: 2 tests OK.

- [ ] **Step 5: Verificar (no lugar de commit)**

Run: `./.venv/Scripts/python.exe manage.py test tickets 2>&1 | tail -3`
Expected: `OK` com a contagem anterior + 2. Run também: `./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.

---

### Task 2: filtro `awaiting`

**Files:**
- Modify: `tickets/filter.py`
- Test: `tickets/tests.py` (classe nova `TicketFilterAwaitingTests`)

**Interfaces:**
- Consumes: `TicketStatus.is_default`, `Ticket.closed_at`.
- Produces: query param `awaiting=true|false` em `GET /tickets/`.

- [ ] **Step 1: Escrever o teste que falha**

No fim de `tickets/tests.py`:

```python
class TicketFilterAwaitingTests(APITestCase):
    """HD-31 (dashboard): `awaiting=true` = em aberto E na situação padrão
    (ninguém pegou); `awaiting=false` = em aberto E fora da padrão (em
    andamento, espera de material...). Os dois EXCLUEM fechados — os blocos da
    home que usam isto são "em aberto" por definição."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Baixa')
        self.st_default = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.st_progress = TicketStatus.objects.create(name='Em andamento', is_in_progress=True)
        self.st_neutral = TicketStatus.objects.create(name='Espera de Material')
        self.st_final = TicketStatus.objects.create(name='Fechado', is_final=True)

        def mk(subject, st, closed=False):
            return Ticket.objects.create(
                user_id=OWNER_ID, subject=subject, type_of_ticket=self.ttype,
                priority=self.prio, status=st,
                closed_at=timezone.now() if closed else None,
            )

        mk('padrao aberto', self.st_default)
        mk('andamento', self.st_progress)
        mk('espera material', self.st_neutral)
        mk('fechado', self.st_final, closed=True)
        # Dado ruim de propósito: fechado mas ainda na situação padrão.
        mk('fechado na padrao', self.st_default, closed=True)
        self.client.force_authenticate(user=make_user())

    def _subjects(self, **params):
        resp = self.client.get(reverse('ticket-list'), params)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return {t['subject'] for t in resp.data['results']}

    def test_awaiting_true_is_default_status_and_open(self):
        self.assertEqual(self._subjects(awaiting='true'), {'padrao aberto'})

    def test_awaiting_false_is_open_outside_default_status(self):
        self.assertEqual(
            self._subjects(awaiting='false'), {'andamento', 'espera material'}
        )

    def test_without_param_everything_still_comes(self):
        self.assertEqual(len(self._subjects()), 5)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe manage.py test tickets.tests.TicketFilterAwaitingTests -v 2`
Expected: os dois primeiros FAIL (sem o filtro, o django-filter ignora o param e devolve os 5). O terceiro PASS.

- [ ] **Step 3: Implementar**

Em `tickets/filter.py`, dentro de `TicketFilter`, logo depois de `is_open`:

```python
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
```

E o método, depois de `filter_is_open`:

```python
    def filter_awaiting(self, queryset, name, value):
        open_qs = queryset.filter(closed_at__isnull=True)
        if value:
            return open_qs.filter(status__is_default=True)
        return open_qs.exclude(status__is_default=True)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe manage.py test tickets.tests.TicketFilterAwaitingTests -v 2`
Expected: 3 tests OK.

- [ ] **Step 5: Verificar**

Run: `./.venv/Scripts/python.exe manage.py test tickets 2>&1 | tail -3`
Expected: `OK`.

---

### Task 3: filtro `has_news`

**Files:**
- Modify: `tickets/filter.py` (imports + filtro + método)
- Test: `tickets/tests.py` (classe nova `TicketFilterHasNewsTests`)

**Interfaces:**
- Consumes: `TicketView.viewed_at` com a semântica da Task 1; `TicketComment` (`ticket`, `user_id`, `created_at`); `Ticket.updated_at` (`auto_now`), `Ticket.closed_at`; `ticket_visibility_q` aplicado pelo `get_queryset` (o filtro recebe o queryset já filtrado).
- Produces: query param `has_news=true|false` em `GET /tickets/`.

- [ ] **Step 1: Escrever o teste que falha**

No fim de `tickets/tests.py`:

```python
class TicketFilterHasNewsTests(APITestCase):
    """HD-31 (dashboard): `has_news=true` = em aberto E (nunca abri OU houve
    atividade depois da minha última abertura). Atividade = alteração no
    chamado (updated_at) ou comentário DE OUTRA PESSOA. Comentário meu não é
    novidade para mim."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Baixa')
        self.st_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.st_final = TicketStatus.objects.create(name='Fechado', is_final=True)
        self.me = make_user(user_id=OWNER_ID)
        self.client.force_authenticate(user=self.me)

    def _ticket(self, subject, closed=False):
        return Ticket.objects.create(
            user_id=OWNER_ID, subject=subject, type_of_ticket=self.ttype,
            priority=self.prio, status=self.st_final if closed else self.st_open,
            closed_at=timezone.now() if closed else None,
        )

    def _viewed(self, ticket, minutes_ago):
        # Registra que EU abri o chamado há N minutos. update() depois do
        # create porque viewed_at é auto_now_add e ignora valor no create.
        view = TicketView.objects.create(ticket=ticket, user_id=OWNER_ID)
        TicketView.objects.filter(pk=view.pk).update(
            viewed_at=timezone.now() - timezone.timedelta(minutes=minutes_ago)
        )

    def _age(self, ticket, minutes_ago):
        # Empurra updated_at para o passado (auto_now não deixa setar no save).
        Ticket.objects.filter(pk=ticket.pk).update(
            updated_at=timezone.now() - timezone.timedelta(minutes=minutes_ago)
        )

    def _comment(self, ticket, by):
        return TicketComment.objects.create(
            ticket=ticket, user_id=by, user_name='Alguem', body='oi',
        )

    def _news(self):
        resp = self.client.get(reverse('ticket-list'), {'has_news': 'true'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return {t['subject'] for t in resp.data['results']}

    def test_never_opened_is_news(self):
        self._ticket('nunca abri')
        self.assertEqual(self._news(), {'nunca abri'})

    def test_opened_and_nothing_happened_is_not_news(self):
        t = self._ticket('quieto')
        self._age(t, 30)
        self._viewed(t, 10)
        self.assertEqual(self._news(), set())

    def test_other_person_comment_after_my_view_is_news(self):
        t = self._ticket('comentaram')
        self._age(t, 30)
        self._viewed(t, 10)
        self._comment(t, by=OTHER_ID)  # agora > viewed_at
        self.assertEqual(self._news(), {'comentaram'})

    def test_my_own_comment_is_not_news(self):
        t = self._ticket('eu comentei')
        self._age(t, 30)
        self._viewed(t, 10)
        self._comment(t, by=OWNER_ID)
        self.assertEqual(self._news(), set())

    def test_ticket_edited_after_my_view_is_news(self):
        t = self._ticket('editaram')
        self._viewed(t, 10)
        # updated_at = agora (auto_now no create) > viewed_at (10 min atrás)
        self.assertEqual(self._news(), {'editaram'})

    def test_closed_ticket_with_new_comment_is_not_news(self):
        t = self._ticket('fechado', closed=True)
        self._age(t, 30)
        self._viewed(t, 10)
        self._comment(t, by=OTHER_ID)
        self.assertEqual(self._news(), set())

    def test_out_of_scope_ticket_with_news_is_not_listed(self):
        # Chamado de outra pessoa, outro setor, sem cópia/acompanhante: fora do
        # meu escopo. Tem novidade (nunca abri), mas não pode aparecer —
        # prova que o filtro parte do get_queryset já filtrado.
        Ticket.objects.create(
            user_id=OTHER_ID, subject='alheio', type_of_ticket=self.ttype,
            priority=self.prio, status=self.st_open,
            sector_id=uuid.uuid4(),
        )
        self.assertEqual(self._news(), set())
```

`uuid` precisa estar importado no topo de `tests.py` (`import uuid`). Confira com `grep -n "^import uuid" tickets/tests.py`; se não houver, adicione. `TicketComment` e `TicketView` devem estar no bloco `from .models import (...)`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe manage.py test tickets.tests.TicketFilterHasNewsTests -v 2`
Expected: os testes que esperam conjunto vazio FAIL (sem o filtro, tudo volta), `test_never_opened_is_news` e os que esperam um subject PASS por coincidência. Confirme que **pelo menos 4 falham**.

- [ ] **Step 3: Implementar**

Em `tickets/filter.py`, trocar os imports do topo por:

```python
import django_filters
from django.db.models import F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest

from .models import Ticket, TicketComment, TicketView
```

Dentro de `TicketFilter`, depois de `awaiting`:

```python
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
```

E o método:

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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe manage.py test tickets.tests.TicketFilterHasNewsTests -v 2`
Expected: 7 tests OK.

- [ ] **Step 5: Mutation check (prova que os testes guardam o comportamento)**

Troque temporariamente `.exclude(user_id=user_id)` por `.filter(user_id=user_id)` em `filter_has_news`, rode a classe: `test_my_own_comment_is_not_news` **tem que falhar**. Desfaça a troca (edite de volta — **não** use `git checkout`, há outras mudanças não commitadas no arquivo) e rode de novo: OK.

Depois, em `views.py`, troque `update_or_create` por `get_or_create` (removendo `defaults`), rode `TicketViewTouchTests`: `test_second_open_moves_viewed_at_forward` **tem que falhar**. Desfaça e confirme OK.

- [ ] **Step 6: Verificar**

Run: `./.venv/Scripts/python.exe manage.py test authentication tickets notifications 2>&1 | tail -3`
Expected: `OK`, contagem anterior + 12 (2 + 3 + 7).
Run: `./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
Run: `git -C . status --short` → só `tickets/views.py`, `tickets/filter.py`, `tickets/tests.py` e os docs em `docs/superpowers/` modificados. **Não commitar.**

---

### Task 4: sonda manual (com os serviços de pé)

Sem código. Serve para pegar o que teste unitário não pega: o `str` vs `UUID` na fronteira do JWT real.

- [ ] **Step 1:** Logado como um usuário com setor, chamar direto no navegador (ou `curl` com o cookie) `http://localhost:8002/api/v1/tickets/?awaiting=true&sector_id=<uuid do setor>` e conferir que a lista bate com o que a tela `/tickets` mostra em "Aberto" para esse setor.
- [ ] **Step 2:** `.../tickets/?has_news=true` → abrir um dos chamados listados na tela → repetir a chamada → ele sumiu. Outro usuário comenta nele → repetir → ele voltou.
- [ ] **Step 3:** Se o passo 2 não sumir o chamado depois de abrir, a suspeita é o `user_id` do `TicketView` vs. o `id` do JWT — confira `TicketView.objects.filter(user_id=<id do JWT>)` no shell.

---

## Self-review

**Cobertura da spec:** Mudança 1 → Task 1; Mudança 2 (`has_news`) → Task 3; Mudança 3 (`awaiting`) → Task 2; testes listados na spec → cada classe tem os casos nomeados na spec, um a um; mutation check → Task 3 Step 5; dívida do `/stats/` → fora do plano por decisão da spec.

**Placeholders:** nenhum — todo passo de código mostra o código; todo passo de teste mostra o teste e o comando.

**Consistência de tipos:** `filter_awaiting`/`filter_has_news` seguem a assinatura `(self, queryset, name, value)` do django-filter, igual ao `filter_is_open` existente. Imports novos em `filter.py` cobrem tudo que os métodos usam (`F`, `OuterRef`, `Q`, `Subquery`, `Coalesce`, `Greatest`, `TicketComment`, `TicketView`).
