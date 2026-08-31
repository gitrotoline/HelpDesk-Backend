# Acompanhantes de chamado — Plano de implementação (backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que setores (ou um departamento inteiro) acompanhem um chamado — vendo e recebendo os marcos — sem alterar quem é o responsável.

**Architecture:** Um modelo `TicketWatcher` guarda os acompanhantes. Departamento é expandido nos setores dele no momento da escrita, guardando uma linha de origem. A visibilidade ganha um `OR` em `ticket_visibility_q`; a notificação reusa `notify_sector`. Comentar já valida visibilidade na escrita, então o acompanhante passa a poder comentar sem código novo.

**Tech Stack:** Django + DRF, `django_filters`, testes com `APITestCase` e `force_authenticate` com `RemoteUser` (usuários vêm do auth-server via JWT; não há User local).

**Spec:** `docs/superpowers/specs/2026-08-31-acompanhantes-de-chamado-backend-design.md`
**Par no frontend:** `frontend/docs/superpowers/plans/2026-08-31-acompanhantes-de-chamado.md`

## Global Constraints

- Jira **HD-31**. Toda mensagem de commit começa com `HD-31 `.
- Nenhuma dependência nova. Nenhuma mudança no auth-server.
- O `Ticket.sector_id` (responsável) **não muda de significado** — nem em
  `_assert_can_close`, nem nos filtros, nem na listagem.
- **Princípio das sobreposições:** escolha explícita ganha de expansão automática,
  e ninguém perde acesso pela remoção de algo que não escolheu.
- Comentário **não** notifica acompanhante. Ninguém é notificado da própria ação
  (já garantido dentro do `notify()`, commit `6b036de`).
- Comandos rodam da raiz do backend com o venv:
  `.venv/Scripts/python.exe manage.py test tickets`
- Comentários em português explicando o *porquê*.

---

### Task 1: Modelo `TicketWatcher`

**Files:**
- Modify: `tickets/models.py` (classe nova no fim do arquivo)
- Modify: `tickets/admin.py` (registro)
- Create: `tickets/migrations/000X_ticketwatcher.py` (gerada por `makemigrations`)
- Test: `tickets/tests.py`

**Interfaces:**
- Produces: `TicketWatcher` com as constantes `KIND_SECTOR`, `KIND_DEPARTMENT`, `ORIGIN_MANUAL`, `ORIGIN_DEPARTMENT`, `ORIGIN_MENTION` e o `related_name='watchers'` — usados por todas as tasks seguintes.

- [ ] **Step 1: Escrever o teste que falha**

Adicionar no fim de `tickets/tests.py`:

```python
class TicketWatcherModelTests(APITestCase):
    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )

    def test_watcher_defaults_and_uniqueness(self):
        sector_id = '44444444-4444-4444-4444-444444444444'
        watcher = TicketWatcher.objects.create(
            ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
            target_id=sector_id, target_name='Elétrica',
        )
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)
        self.assertEqual(watcher.source_ref, '')
        self.assertIn(watcher, self.ticket.watchers.all())
        with self.assertRaises(IntegrityError):
            TicketWatcher.objects.create(
                ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
                target_id=sector_id, target_name='Elétrica (duplicado)',
            )
```

Acrescentar aos imports do topo do arquivo: `from django.db.utils import IntegrityError`
e `TicketWatcher` na lista importada de `.models`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.TicketWatcherModelTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'TicketWatcher'`

- [ ] **Step 3: Criar o modelo**

Em `tickets/models.py`, no fim do arquivo:

```python
class TicketWatcher(models.Model):
    """Setor (ou departamento) acompanhando o chamado: vê e recebe os marcos, mas
    não é o responsável — quem atende e fecha continua sendo o Ticket.sector_id.
    Pessoa em cópia continua no TicketRecipient."""

    KIND_SECTOR = 'sector'
    KIND_DEPARTMENT = 'department'
    KIND_CHOICES = [(KIND_SECTOR, 'Setor'), (KIND_DEPARTMENT, 'Departamento')]

    ORIGIN_MANUAL = 'manual'
    ORIGIN_DEPARTMENT = 'department'
    ORIGIN_MENTION = 'mention'
    ORIGIN_CHOICES = [
        (ORIGIN_MANUAL, 'Escolhido'),
        (ORIGIN_DEPARTMENT, 'Veio do departamento'),
        (ORIGIN_MENTION, 'Veio de uma menção'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='watchers')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    # id do setor/departamento no auth-server: sem FK, a entidade é remota (mesmo
    # padrão do Ticket.sector_id + sector_name).
    target_id = models.UUIDField()
    target_name = models.CharField(max_length=150, blank=True, default='')
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default=ORIGIN_MANUAL)
    # De onde veio: UUID do departamento (origin=department) ou pk do chamado
    # mencionado (origin=mention). CharField pelo mesmo motivo do
    # Notification.target_id — guarda referências de tipos diferentes.
    source_ref = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_watcher'
        verbose_name = 'Ticket Watcher'
        verbose_name_plural = 'Ticket Watchers'
        constraints = [
            models.UniqueConstraint(fields=['ticket', 'kind', 'target_id'],
                                    name='unique_ticket_watcher')
        ]
        indexes = [models.Index(fields=['ticket', 'kind'])]

    def __str__(self):
        return f'#{self.ticket_id} - {self.target_name or self.target_id}'
```

Em `tickets/admin.py`, seguindo o estilo dos registros existentes:

```python
@admin.register(TicketWatcher)
class TicketWatcherAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'kind', 'target_name', 'origin', 'created_at')
    list_filter = ('kind', 'origin')
    search_fields = ('target_name',)
    readonly_fields = ('created_at',)
```

- [ ] **Step 4: Gerar a migration**

Run: `.venv/Scripts/python.exe manage.py makemigrations tickets`
Expected: cria `tickets/migrations/000X_ticketwatcher.py` com `CreateModel`. Nenhuma
alteração em modelo existente deve aparecer — se aparecer, pare e investigue.

- [ ] **Step 5: Rodar os testes**

Run: `.venv/Scripts/python.exe manage.py test tickets`
Expected: OK, com o teste novo passando.

- [ ] **Step 6: Commit**

```bash
git add tickets/models.py tickets/admin.py tickets/migrations/ tickets/tests.py
git commit -m "HD-31 Ticket - Modelo de acompanhante do chamado"
```

---

### Task 2: Expansão do departamento em setores

**Files:**
- Modify: `sector/services.py`
- Test: `tickets/tests.py`

**Interfaces:**
- Consumes: `list_sectors(params, auth_header)` já existente no mesmo arquivo.
- Produces: `list_department_sectors(department_id, auth_header) -> list | None`
  — lista de `{'id', 'name'}`; **`None` significa falha de consulta**, `[]` significa
  departamento sem setor ativo. A Task 3 depende dessa distinção.

- [ ] **Step 1: Escrever os testes que falham**

```python
class DepartmentSectorsServiceTests(APITestCase):
    """A distinção entre falha e vazio é o ponto deste serviço: `list_sectors`
    devolve [] em erro de rede, o que aqui viraria 'departamento sem setores' e
    faria o backend gravar zero acompanhantes achando que deu certo."""

    @patch('sector.services.requests.get')
    def test_returns_sectors_of_department(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'data': [{'id': 'aaa', 'name': 'Elétrica'}, {'id': 'bbb', 'name': 'Mecânica'}]
        }
        result = list_department_sectors('dept-uuid', 'Bearer x')
        self.assertEqual([s['name'] for s in result], ['Elétrica', 'Mecânica'])

    @patch('sector.services.requests.get', side_effect=requests.RequestException('down'))
    def test_returns_none_on_network_error(self, _get):
        # None = não deu para consultar. Diferente de [] (consultou, veio vazio).
        self.assertIsNone(list_department_sectors('dept-uuid', 'Bearer x'))

    @patch('sector.services.requests.get')
    def test_returns_none_on_bad_status(self, mock_get):
        mock_get.return_value.status_code = 500
        self.assertIsNone(list_department_sectors('dept-uuid', 'Bearer x'))

    @patch('sector.services.requests.get')
    def test_returns_empty_list_when_department_has_no_sectors(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'data': []}
        self.assertEqual(list_department_sectors('dept-uuid', 'Bearer x'), [])
```

Imports a acrescentar no topo de `tickets/tests.py`: `import requests` e
`from sector.services import list_department_sectors`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.DepartmentSectorsServiceTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'list_department_sectors'`

- [ ] **Step 3: Implementar o serviço**

Em `sector/services.py`, depois de `list_sectors`:

```python
def list_department_sectors(department_id, auth_header: str | None = None) -> list | None:
    """Setores ATIVOS de um departamento (GET /sectors/?department_id=&is_active=true).

    Devolve None quando não deu para consultar (rede ou status != 200) e [] quando
    o departamento realmente não tem setor ativo. A diferença importa: quem chama
    grava acompanhantes a partir daqui, e tratar falha como lista vazia gravaria
    zero acompanhantes respondendo sucesso — o usuário acharia que deu acesso ao
    departamento inteiro e ninguém teria recebido nada.

    Por isso NÃO reusa list_sectors: aquele engole o erro de propósito, porque
    serve para popular dropdown, onde degradar é o certo.
    """
    if not department_id:
        return []

    url = f'{base_url()}/sectors/'
    params = {'department_id': str(department_id), 'is_active': 'true'}

    try:
        r = requests.get(url, headers=headers(auth_header), params=params, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('list_department_sectors(%s) falhou: %s', department_id, exc)
        return None

    if r.status_code != 200:
        logger.warning('list_department_sectors(%s) retornou status %s', department_id, r.status_code)
        return None

    body = r.json()
    # O SectorViewSet.list do auth-server devolve {'data': [...]} sem paginação.
    items = body.get('data', []) if isinstance(body, dict) else body
    return [{'id': s['id'], 'name': s.get('name', '')} for s in items if s.get('id')]
```

- [ ] **Step 4: Rodar os testes**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.DepartmentSectorsServiceTests -v 2`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add sector/services.py tickets/tests.py
git commit -m "HD-31 Setor - Lista setores ativos de um departamento"
```

---

### Task 3: Rotas de adicionar e remover acompanhante

**Files:**
- Modify: `tickets/serializer.py` (`TicketWatcherSerializer`; `watchers` no `TicketDetailSerializer`)
- Modify: `tickets/views.py` (duas `@action` no `TicketViewSet`)
- Test: `tickets/tests.py`

**Interfaces:**
- Consumes: `TicketWatcher` (Task 1), `list_department_sectors` (Task 2), `_assert_can_edit` já existente no `TicketViewSet`.
- Produces: `POST /tickets/{id}/watchers/`, `DELETE /tickets/{id}/watchers/{watcher_id}/`, e o campo `watchers` no detalhe — consumidos pelo frontend.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TicketWatcherApiTests(APITestCase):
    DEPT = '55555555-5555-5555-5555-555555555555'
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'
    SEC_B = 'aaaaaaa1-0000-0000-0000-000000000002'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())
        self.url = reverse('ticket-watchers', args=[self.ticket.id])

    @patch('tickets.views.notify_sector')
    def test_add_sector_watcher(self, _ns):
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        watcher = TicketWatcher.objects.get(ticket=self.ticket)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_add_department_expands_and_keeps_origin_row(self, mock_list, _ns):
        mock_list.return_value = [
            {'id': self.SEC_A, 'name': 'Elétrica'}, {'id': self.SEC_B, 'name': 'Mecânica'},
        ]
        resp = self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # 1 linha de origem (departamento) + 1 por setor expandido.
        self.assertEqual(self.ticket.watchers.filter(kind='department').count(), 1)
        derived = self.ticket.watchers.filter(kind='sector')
        self.assertEqual(derived.count(), 2)
        self.assertTrue(all(w.origin == TicketWatcher.ORIGIN_DEPARTMENT for w in derived))
        self.assertTrue(all(str(w.source_ref) == self.DEPT for w in derived))

    @patch('tickets.views.list_department_sectors', return_value=None)
    def test_department_expansion_failure_returns_502_and_saves_nothing(self, _m):
        resp = self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(self.ticket.watchers.count(), 0)

    @patch('tickets.views.list_department_sectors', return_value=[])
    def test_department_without_active_sectors_returns_400(self, _m):
        resp = self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.ticket.watchers.count(), 0)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_expansion_does_not_downgrade_manual_sector(self, mock_list, _ns):
        # Escolha explícita ganha de expansão automática.
        TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A,
            target_name='Elétrica', origin=TicketWatcher.ORIGIN_MANUAL,
        )
        mock_list.return_value = [{'id': self.SEC_A, 'name': 'Elétrica'}]
        self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        watcher = self.ticket.watchers.get(kind='sector', target_id=self.SEC_A)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)

    @patch('tickets.views.notify_sector')
    def test_adding_manually_promotes_derived_sector(self, _ns):
        TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A, target_name='Elétrica',
            origin=TicketWatcher.ORIGIN_DEPARTMENT, source_ref=self.DEPT,
        )
        self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        watcher = self.ticket.watchers.get(kind='sector', target_id=self.SEC_A)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)
        self.assertEqual(watcher.source_ref, '')

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_removing_department_keeps_promoted_sector(self, mock_list, _ns):
        mock_list.return_value = [
            {'id': self.SEC_A, 'name': 'Elétrica'}, {'id': self.SEC_B, 'name': 'Mecânica'},
        ]
        self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})  # promove A
        dept_row = self.ticket.watchers.get(kind='department')
        detail = reverse('ticket-watcher-detail', args=[self.ticket.id, dept_row.id])
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        remaining = list(self.ticket.watchers.values_list('target_id', flat=True))
        self.assertEqual([str(t) for t in remaining], [self.SEC_A])  # B saiu, A ficou

    def test_detail_exposes_watchers(self):
        TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A, target_name='Elétrica',
        )
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertEqual([w['target_name'] for w in resp.data['watchers']], ['Elétrica'])

    def test_outsider_cannot_manage_watchers(self):
        self.client.force_authenticate(user=make_user(user_id=OTHER_ID))
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.TicketWatcherApiTests -v 2`
Expected: FAIL — `NoReverseMatch: 'ticket-watchers' is not a valid view function or pattern name`

- [ ] **Step 3: Serializer de leitura**

Em `tickets/serializer.py`, antes do `TicketDetailSerializer`:

```python
class TicketWatcherSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketWatcher
        fields = ['id', 'kind', 'target_id', 'target_name', 'origin', 'source_ref']
```

E no `TicketDetailSerializer`, junto dos campos de relacionados:

```python
    watchers = TicketWatcherSerializer(many=True, read_only=True)
```

Acrescentar `TicketWatcher` ao import de `.models` no topo do arquivo.

- [ ] **Step 4: As duas actions**

Em `tickets/views.py`, no `TicketViewSet` (imports novos: `TicketWatcher` de
`.models`, `list_department_sectors` de `sector.services`):

```python
    # url_name explícito: sem ele o nome da rota seria 'ticket-add-watcher'
    # (DRF deriva do nome do método), e os testes usam reverse('ticket-watchers').
    @action(detail=True, methods=['post'], url_path='watchers', url_name='watchers')
    def add_watcher(self, request, pk=None):
        """Inclui um setor — ou um departamento, que é expandido nos setores dele."""
        ticket = self.get_object()
        self._assert_can_edit(ticket)
        kind = request.data.get('kind')
        target_id = request.data.get('target_id')
        if kind not in (TicketWatcher.KIND_SECTOR, TicketWatcher.KIND_DEPARTMENT) or not target_id:
            return Response({'detail': 'kind e target_id são obrigatórios.'},
                            status=http_status.HTTP_400_BAD_REQUEST)

        if kind == TicketWatcher.KIND_SECTOR:
            self._upsert_sector_watcher(ticket, target_id, request.data.get('target_name', ''),
                                        TicketWatcher.ORIGIN_MANUAL, '')
        else:
            # None = não deu para consultar; [] = departamento sem setor ativo.
            # Tratar os dois como vazio gravaria zero acompanhantes com resposta
            # de sucesso, e o usuário acharia que deu acesso ao departamento.
            sectors = list_department_sectors(target_id, request.user.auth_header)
            if sectors is None:
                return Response(
                    {'detail': 'Não foi possível consultar os setores do departamento.'},
                    status=http_status.HTTP_502_BAD_GATEWAY,
                )
            if not sectors:
                return Response({'detail': 'Este departamento não tem setores ativos.'},
                                status=http_status.HTTP_400_BAD_REQUEST)
            TicketWatcher.objects.get_or_create(
                ticket=ticket, kind=TicketWatcher.KIND_DEPARTMENT, target_id=target_id,
                defaults={'target_name': request.data.get('target_name', ''),
                          'origin': TicketWatcher.ORIGIN_MANUAL},
            )
            for sector in sectors:
                self._upsert_sector_watcher(ticket, sector['id'], sector.get('name', ''),
                                            TicketWatcher.ORIGIN_DEPARTMENT, str(target_id))

        self._notify_watchers(ticket, f'Você foi incluído no chamado #{ticket.pk}')
        return Response(self.get_serializer(ticket).data, status=http_status.HTTP_201_CREATED)

    def _upsert_sector_watcher(self, ticket, sector_id, name, origin, source_ref):
        """Grava o acompanhante de setor respeitando o princípio: escolha explícita
        (manual) ganha de expansão automática. Manual promove o que era derivado;
        derivado nunca rebaixa o que era manual."""
        watcher, created = TicketWatcher.objects.get_or_create(
            ticket=ticket, kind=TicketWatcher.KIND_SECTOR, target_id=sector_id,
            defaults={'target_name': name, 'origin': origin, 'source_ref': source_ref},
        )
        if not created and origin == TicketWatcher.ORIGIN_MANUAL \
                and watcher.origin != TicketWatcher.ORIGIN_MANUAL:
            watcher.origin = TicketWatcher.ORIGIN_MANUAL
            watcher.source_ref = ''
            watcher.save(update_fields=['origin', 'source_ref'])
        return watcher

    @action(detail=True, methods=['delete'],
            url_path=r'watchers/(?P<watcher_id>[^/.]+)', url_name='watcher-detail')
    def remove_watcher(self, request, pk=None, watcher_id=None):
        """Remove o acompanhante. Removendo um departamento saem também os setores
        que ELE gerou — os promovidos a manual ficam, porque foram escolhidos."""
        ticket = self.get_object()
        self._assert_can_edit(ticket)
        watcher = get_object_or_404(TicketWatcher, ticket=ticket, pk=watcher_id)
        if watcher.kind == TicketWatcher.KIND_DEPARTMENT:
            TicketWatcher.objects.filter(
                ticket=ticket, kind=TicketWatcher.KIND_SECTOR,
                origin=TicketWatcher.ORIGIN_DEPARTMENT, source_ref=str(watcher.target_id),
            ).delete()
        watcher.delete()
        return Response(status=http_status.HTTP_204_NO_CONTENT)
```

O `_notify_watchers` chega na Task 5. Até lá, use um stub no topo da classe para
os testes rodarem:

```python
    def _notify_watchers(self, ticket, message):
        pass  # implementado na Task 5
```

- [ ] **Step 5: Rodar os testes**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.TicketWatcherApiTests -v 2`
Expected: PASS (9 testes)

- [ ] **Step 6: Suíte completa**

Run: `.venv/Scripts/python.exe manage.py test tickets`
Expected: OK

- [ ] **Step 7: Commit**

```bash
git add tickets/serializer.py tickets/views.py tickets/tests.py
git commit -m "HD-31 Ticket - Rotas de acompanhante e leitura no detalhe"
```

---

### Task 4: Visibilidade (a tarefa de risco)

**Files:**
- Modify: `tickets/scope.py`
- Test: `tickets/tests.py`

**Interfaces:**
- Consumes: `TicketWatcher` (Task 1).
- Produces: nada de novo em assinatura — muda o comportamento de
  `ticket_visibility_q`, que é usado pelo `TicketViewSet`, pelo
  `TicketCommentViewSet` e pelo `TicketDetailSerializer._related`.

- [ ] **Step 1: Escrever os testes que falham**

`make_user` não define setor. Para estes testes, crie o usuário com setor:

```python
def make_user_with_sector(user_id, sector_id, sector_name='Elétrica'):
    # O RemoteUser lê o setor do claim `sector` do JWT (authentication/auth.py).
    return RemoteUser({
        'user_id': str(user_id), 'first_name': 'Test', 'last_name': 'User',
        'is_superuser': False, 'permissions': [],
        'sector': {'id': str(sector_id), 'name': sector_name},
    })


class WatcherVisibilityTests(APITestCase):
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='Do outro', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        # OTHER_ID é de outro setor: sem acompanhar, não vê nada deste chamado.
        self.outsider = make_user_with_sector(OTHER_ID, self.SEC_A)

    def _watch(self, kind=TicketWatcher.KIND_SECTOR, target_id=None):
        return TicketWatcher.objects.create(
            ticket=self.ticket, kind=kind, target_id=target_id or self.SEC_A,
            target_name='Elétrica',
        )

    def test_watcher_sector_member_sees_ticket(self):
        self._watch()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual([t['id'] for t in resp.data['results']], [self.ticket.id])

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_watcher_sector_member_can_comment(self, _n, _ns):
        # Consequência da visibilidade: o perform_create do comentário valida escopo.
        self._watch()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.post(
            reverse('ticket-comment-list'), {'ticket': self.ticket.id, 'body': 'ajudo aqui'}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_department_row_alone_grants_nothing(self):
        # A linha de departamento é só registro de origem: o token traz setor, não
        # departamento, então ela nunca casa com ninguém. Quem dá acesso são os
        # setores expandidos.
        self._watch(kind=TicketWatcher.KIND_DEPARTMENT,
                    target_id='55555555-5555-5555-5555-555555555555')
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 0)

    def test_removing_watcher_removes_access(self):
        watcher = self._watch()
        watcher.delete()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 0)

    def test_ticket_is_not_duplicated_in_listing(self):
        # O Q agora faz JOIN com recipients E watchers: sem distinct(), o mesmo
        # chamado apareceria repetido para quem casa em mais de um caminho.
        self._watch()
        TicketRecipient.objects.create(ticket=self.ticket, user_id=OTHER_ID)
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 1)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.WatcherVisibilityTests -v 2`
Expected: FAIL nos testes 1, 2 e 5 (o chamado não aparece / comentário 403).
Os testes 3 e 4 já passam — são trava de regressão.

- [ ] **Step 3: Implementar**

Em `tickets/scope.py`, dentro de `ticket_visibility_q`, junto do bloco que já
adiciona o setor do usuário:

```python
    if user.sector and user.sector.id:
        scope |= Q(**{field('sector_id'): user.sector.id})
        # Acompanhantes: só as linhas de setor concedem acesso. A linha de
        # departamento é registro de origem — o token traz setor, não
        # departamento, então ela nunca casaria com ninguém.
        scope |= Q(**{field('watchers__kind'): 'sector',
                      field('watchers__target_id'): user.sector.id})
```

- [ ] **Step 4: Rodar os testes**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.WatcherVisibilityTests -v 2`
Expected: PASS (5 testes)

- [ ] **Step 5: Prova por mutação**

Comente a linha `scope |= Q(**{field('watchers__kind')...})` e rode de novo:

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.WatcherVisibilityTests -v 2`
Expected: **FAIL** nos testes `test_watcher_sector_member_sees_ticket` e
`test_watcher_sector_member_can_comment`.

Se passar tudo com a linha comentada, os testes não estão provando nada — pare e
conserte os testes antes de seguir. **Descomente a linha** depois da prova.

- [ ] **Step 6: Suíte completa**

Run: `.venv/Scripts/python.exe manage.py test tickets`
Expected: OK — atenção especial aos testes de escopo que já existiam
(`test_related_out_of_scope_is_hidden_but_pk_still_listed`,
`test_outsider_cannot_comment_on_invisible_ticket`).

- [ ] **Step 7: Commit**

```bash
git add tickets/scope.py tickets/tests.py
git commit -m "HD-31 Ticket - Acompanhante enxerga o chamado"
```

---

### Task 5: Notificação dos marcos

**Files:**
- Modify: `tickets/views.py` (`_notify_watchers` real, chamadas em `close`/`reopen`)
- Test: `tickets/tests.py`

**Interfaces:**
- Consumes: `notify_sector` de `notifications.services` (já importado no arquivo).
- Produces: `TicketViewSet._notify_watchers(ticket, message)`.

- [ ] **Step 1: Escrever os testes que falham**

```python
class WatcherNotificationTests(APITestCase):
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.status_done = TicketStatus.objects.create(name='Fechado', is_final=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        TicketWatcher.objects.create(
            ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
            target_id=self.SEC_A, target_name='Elétrica',
        )
        self.client.force_authenticate(user=make_user())

    @patch('tickets.views.notify')
    @patch('tickets.views.notify_sector')
    def test_close_notifies_watcher_sectors(self, mock_sector, _n):
        self.client.post(reverse('ticket-close', args=[self.ticket.id]))
        notified = [str(call.args[0]) for call in mock_sector.call_args_list]
        self.assertIn(self.SEC_A, notified)

    @patch('tickets.views.notify')
    @patch('tickets.views.notify_sector')
    def test_comment_does_not_notify_watcher_sectors(self, mock_sector, _n):
        # Decisão explícita: acompanhante recebe marcos, não conversa. Um
        # departamento acompanhando viraria dezenas de notificações por thread.
        self.client.post(
            reverse('ticket-comment-list'), {'ticket': self.ticket.id, 'body': 'oi'}
        )
        notified = [str(call.args[0]) for call in mock_sector.call_args_list]
        self.assertNotIn(self.SEC_A, notified)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.WatcherNotificationTests -v 2`
Expected: FAIL em `test_close_notifies_watcher_sectors` (o setor acompanhante não é
notificado). O segundo teste já passa — é trava de regressão do silêncio.

- [ ] **Step 3: Implementar**

Substituir o stub em `tickets/views.py`:

```python
    def _notify_watchers(self, ticket, message):
        """Marcos para os setores acompanhantes. Só linhas kind='sector': a de
        departamento é registro de origem, e os setores dela já estão gravados.
        Best-effort, como o _notify_sector — falha de rede não derruba a ação.
        Quem agiu não se notifica: a regra vive dentro do notify()."""
        for target_id in ticket.watchers.filter(
            kind=TicketWatcher.KIND_SECTOR
        ).values_list('target_id', flat=True):
            notify_sector(
                target_id, 'ticket', ticket.pk, message,
                self.request.user, self.request.user.auth_header,
            )
```

E chamar em `close` e `reopen`, logo após o `notify` que já existe em cada um:

```python
        self._notify_watchers(ticket, f'Ticket #{ticket.pk} foi fechado')
```
```python
        self._notify_watchers(ticket, f'Ticket #{ticket.pk} foi reaberto')
```

- [ ] **Step 4: Rodar os testes**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.WatcherNotificationTests -v 2`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add tickets/views.py tickets/tests.py
git commit -m "HD-31 Ticket - Notifica acompanhantes nos marcos"
```

---

### Task 6: Menção inclui o setor como acompanhante

**Files:**
- Modify: `tickets/serializer.py` (`TicketSerializer.create` e `.update`)
- Test: `tickets/tests.py`

**Interfaces:**
- Consumes: `TicketWatcher` (Task 1).
- Produces: nada de novo em assinatura.

- [ ] **Step 1: Escrever os testes que falham**

```python
class MentionWatcherTests(APITestCase):
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # O chamado mencionado tem setor: é ele que vira acompanhante.
        self.mentioned = Ticket.objects.create(
            user_id=OWNER_ID, subject='Origem', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id=self.SEC_A, sector_name='Elétrica',
        )
        self.client.force_authenticate(user=make_user())

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_creating_with_mention_adds_watcher(self, _n, _ns):
        resp = self.client.post(reverse('ticket-list'), {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id, 'priority': self.prio.id,
            'status': self.status_open.id, 'sector': '99999999-9999-9999-9999-999999999999',
            'sector_name': 'TI', 'mentions': [self.mentioned.id],
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        watcher = created.watchers.get(kind=TicketWatcher.KIND_SECTOR)
        self.assertEqual(str(watcher.target_id), self.SEC_A)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MENTION)
        self.assertEqual(watcher.source_ref, str(self.mentioned.id))

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_unlinking_mention_keeps_watcher(self, _n, _ns):
        # Tirar acesso em silêncio é pior que sobrar acesso: quem quiser remove à mão.
        created = Ticket.objects.create(
            user_id=OWNER_ID, subject='Novo', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id='99999999-9999-9999-9999-999999999999', sector_name='TI',
        )
        created.mentions.add(self.mentioned)
        TicketWatcher.objects.create(
            ticket=created, kind=TicketWatcher.KIND_SECTOR, target_id=self.SEC_A,
            target_name='Elétrica', origin=TicketWatcher.ORIGIN_MENTION,
            source_ref=str(self.mentioned.id),
        )
        self.client.patch(reverse('ticket-detail', args=[created.id]),
                          {'mentions': []}, format='json')
        self.assertTrue(created.watchers.filter(target_id=self.SEC_A).exists())
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.MentionWatcherTests -v 2`
Expected: FAIL em `test_creating_with_mention_adds_watcher`
(`TicketWatcher.DoesNotExist`). O segundo já passa — trava de regressão.

- [ ] **Step 3: Implementar**

Em `tickets/serializer.py`, no `TicketSerializer`:

```python
    def _sync_mention_watchers(self, ticket, mentioned_tickets):
        """Vincular uma menção inclui o setor do chamado mencionado como
        acompanhante do chamado atual. Direção única: quem foi mencionado NÃO passa
        a acompanhar quem mencionou. Não sobrescreve escolha explícita (manual),
        e desvincular depois não remove — tirar acesso em silêncio é pior que
        sobrar acesso."""
        for mentioned in mentioned_tickets:
            if not mentioned.sector_id:
                continue
            TicketWatcher.objects.get_or_create(
                ticket=ticket, kind=TicketWatcher.KIND_SECTOR,
                target_id=mentioned.sector_id,
                defaults={
                    'target_name': mentioned.sector_name,
                    'origin': TicketWatcher.ORIGIN_MENTION,
                    'source_ref': str(mentioned.pk),
                },
            )
```

Chamar no fim do `create` e do `update`, com as menções resultantes:

```python
        self._sync_mention_watchers(ticket, ticket.mentions.all())
```

O `get_or_create` já garante o "não sobrescreve": se a linha existe como
`manual`, nada muda.

- [ ] **Step 4: Rodar os testes**

Run: `.venv/Scripts/python.exe manage.py test tickets.tests.MentionWatcherTests -v 2`
Expected: PASS (2 testes)

- [ ] **Step 5: Suíte completa dos dois apps**

Run: `.venv/Scripts/python.exe manage.py test tickets notifications`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add tickets/serializer.py tickets/tests.py
git commit -m "HD-31 Ticket - Mencao inclui o setor como acompanhante"
```

---

## Entrega para o frontend

Depois da Task 6, `GET /tickets/{id}/` devolve `watchers`, e as rotas
`POST /tickets/{id}/watchers/` e `DELETE /tickets/{id}/watchers/{watcher_id}/`
estão disponíveis. É o gatilho para o plano do frontend
(`frontend/docs/superpowers/plans/2026-08-31-acompanhantes-de-chamado.md`).
