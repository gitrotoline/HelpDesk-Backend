# Design — Acompanhantes de chamado (backend)

Data: 2026-08-31
App: `tickets` (backend Django + DRF)
Par no frontend: `frontend/docs/superpowers/specs/2026-08-31-acompanhantes-de-chamado-frontend-design.md`
Jira: HD-31

## Objetivo

Hoje um chamado tem exatamente **um** setor (`Ticket.sector_id`), e esse campo
carrega três significados ao mesmo tempo: quem vê (`ticket_visibility_q`), quem é
notificado (`notify_sector`) e quem pode fechar (`_assert_can_close`).

Queremos permitir que outros setores — ou um departamento inteiro — acompanhem um
chamado, **sem** mexer em nenhum desses três significados. O setor do chamado
continua sendo o responsável.

## Decisões tomadas

- **Acompanhante vê e é avisado; não assume o chamado.** O responsável continua
  único: quem atende, quem fecha, o que aparece nos filtros e na listagem.
- **Acompanhante pode comentar.** Ver e participar já andam juntos neste sistema
  (quem está em cópia comenta hoje). O que segue exclusivo do responsável é fechar.
- **Notificação só de marcos**: incluído como acompanhante, chamado fechado,
  chamado reaberto. **Comentário não notifica acompanhante** — um departamento
  acompanhando transformaria uma conversa de 10 mensagens em 10 notificações para
  dezenas de pessoas, e o resultado prático seria o time ignorar o sininho. Quem
  acompanha lê a thread pelo painel de relacionados ou abrindo o chamado.
- **Departamento é açúcar de digitação**: ao adicionar, expande-se nos setores
  ativos dele. Depois de gravado, visibilidade e notificação só enxergam setores.
- **A origem é guardada.** Uma linha `kind='department'` registra que aquilo veio
  do departamento X — sem ela, a tela mostraria "Elétrica, Mecânica, Hidráulica"
  para quem escolheu "Manutenção", e a informação de origem seria irrecuperável.
- **A lista de setores do departamento é congelada** no momento em que se adiciona
  (ver "Congelamento" abaixo).
- **Menção adiciona acompanhante automaticamente**: vincular o chamado 1 ao 2
  insere o setor do 1 como acompanhante do 2. Desvincular **não** remove.
- **Quem gerencia**: dono, membro do setor do chamado, ou admin — o mesmo
  conjunto que pode fechar/reabrir o chamado, via `_assert_can_handle` (HD-31).
  Gerenciar acompanhantes é atender o chamado, não editar seu conteúdo, então
  não usa mais `_assert_can_edit` (que continua reservado a assunto/descrição
  e exclusão, restrito a dono/admin).

## Princípio que resolve as sobreposições

> Escolha explícita ganha de expansão automática, e ninguém perde acesso pela
> remoção de algo que não escolheu.

Dele saem três regras concretas:

- Expandir um departamento **não** sobrescreve um setor que já estava lá como
  avulso — ele continua avulso.
- Remover um departamento leva junto **só** os setores que ele gerou.
- Adicionar avulso um setor que veio de um departamento o **promove** a avulso
  (a origem passa a `manual`).

É o mesmo critério já aceito para a menção: desvincular não remove o acompanhante.

## Fora de escopo (YAGNI)

- Multi-responsável, fechamento parcial por setor, transferência de chamado.
- Preferência por usuário ("quero receber tudo deste chamado").
- Reexpansão automática de departamento (ver "Congelamento").
- `TicketLog` de auditoria para adicionar/remover acompanhante — fácil de somar
  depois; não é pré-requisito de nada aqui.
- Acompanhante em nível de pessoa: já existe, é o `TicketRecipient`, e não muda.

## 1. Modelo — `tickets/models.py`

```python
class TicketWatcher(models.Model):
    """Setor (ou departamento) acompanhando o chamado: vê e recebe os marcos, mas
    não é o responsável. Pessoa em cópia continua no TicketRecipient."""

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
    # id do setor/departamento no auth-server (não há FK: a entidade é remota).
    target_id = models.UUIDField()
    target_name = models.CharField(max_length=150, blank=True, default='')  # snapshot
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

Migration nova em `tickets/migrations/` (não altera nada existente).

## 2. Visibilidade — `tickets/scope.py`

`ticket_visibility_q` ganha **um** `OR`: o usuário vê o chamado se o setor dele
está entre os acompanhantes **do tipo setor**.

```python
scope |= Q(**{field('watchers__kind'): 'sector',
              field('watchers__target_id'): user.sector.id})
```

**A linha `kind='department'` não concede acesso a ninguém.** Ela é só registro de
origem — o token do usuário traz `sector`, não departamento, então não há como
compará-la (ver "Congelamento"). O acesso vem sempre das linhas de setor que ela
gerou. Isso precisa estar coberto por teste: alguém que leia o modelo depois pode
"consertar" incluindo `kind='department'` no `Q` e criar um filtro que nunca casa —
ou pior, que casa errado.

Cuidado herdado: o `Q` já faz JOIN com `recipients`; agora faz também com
`watchers`. O `.distinct()` que já existe no `TicketViewSet.get_queryset` e no
`TicketCommentViewSet.get_queryset` continua obrigatório, e o
`Count('comments', distinct=True)` do `TicketDetailSerializer._related` idem.

**Consequência automática, sem código:** como comentar já valida
`ticket_visibility_q` na escrita (commit `77dd077`), o acompanhante passa a poder
comentar assim que a visibilidade o incluir. Precisa de teste, não de implementação.

## 3. Expansão do departamento — `sector/services.py`

Não exige mudança no auth-server: `SectorFilter` já tem `department_id`, e
`list_sectors(params, auth_header)` já repassa query string.

```python
def list_department_sectors(department_id, auth_header=None):
    """Setores ativos de um departamento (GET /sectors/?department_id=&is_active=true).
    Devolve [{'id','name'}]. O endpoint do auth-server não pagina (SectorViewSet.list
    devolve {'data': [...]} inteiro)."""
```

**A falha não pode ser silenciosa.** `list_sectors` engole erro e devolve `[]` — o
que é correto para popular dropdown e péssimo aqui: auth-server fora do ar
gravaria zero acompanhantes e responderia 201, e o usuário acharia que deu acesso
ao departamento inteiro quando ninguém recebeu nada. É a mesma falha que
corrigimos no `listComments` do frontend (vazio indistinguível de erro).

Portanto a rota de adicionar departamento distingue os dois casos:

| Situação | Resposta |
|---|---|
| Erro de rede/status no auth-server | **502** `Não foi possível consultar os setores do departamento.` |
| Departamento sem setor ativo | **400** `Este departamento não tem setores ativos.` |
| OK | 201 com a lista gravada |

Para isso, `list_department_sectors` **propaga** o erro (exceção ou sentinela
`None`) em vez de devolver `[]` — diferente do `list_sectors`, que continua como
está para os dropdowns.

## 4. API — `tickets/views.py` e `tickets/urls.py`

**Leitura**: `watchers` entra no `TicketDetailSerializer` (só no `retrieve`, mesmo
motivo dos relacionados), com `prefetch_related('watchers')`:

```jsonc
"watchers": [
  {"id": 9,  "kind": "department", "target_id": "…", "target_name": "Manutenção",
   "origin": "manual",     "source_ref": ""},
  {"id": 10, "kind": "sector", "target_id": "…", "target_name": "Elétrica",
   "origin": "department", "source_ref": "<uuid do departamento>"},
  {"id": 11, "kind": "sector", "target_id": "…", "target_name": "TI",
   "origin": "mention",    "source_ref": "12"}
]
```

**Escrita**: sub-rotas no `TicketViewSet`, protegidas por `_assert_can_edit`:

- `POST /tickets/{id}/watchers/` — corpo `{"kind": "sector"|"department", "target_id": "<uuid>"}`.
  - `kind=sector`: grava 1 linha `origin=manual`. Se já existir com
    `origin=department|mention`, **promove** para `manual` (`source_ref=''`).
  - `kind=department`: expande (seção 3), grava a linha do departamento
    (`kind=department, origin=manual`) e uma linha por setor
    (`kind=sector, origin=department, source_ref=<uuid do depto>`), **pulando** os
    setores que já existirem com `origin=manual`.
  - Idempotente: repetir não duplica (constraint) nem erra.
- `DELETE /tickets/{id}/watchers/{watcher_id}/`
  - linha de setor: remove só ela.
  - linha de departamento: remove ela **e** os setores com
    `origin=department, source_ref=<uuid dela>` — preservando os promovidos a manual.

O `target_name` é snapshot no momento da gravação, como `sector_name` no `Ticket`.

## 5. Notificação — `tickets/views.py`

| Evento | Acompanhante recebe? |
|---|---|
| Incluído como acompanhante | **sim** — `Você foi incluído no chamado #N` |
| Chamado fechado | **sim** |
| Chamado reaberto | **sim** |
| Comentário novo | **não** |
| Chamado editado | **não** |

Implementação: helper `_notify_watchers(ticket, message)` que itera as linhas
`kind='sector'` e chama `notify_sector` (que já resolve os membros no auth-server e
é best-effort). Chamado em `close`, `reopen` e ao adicionar.

**Ninguém é notificado da própria ação** — inclusive quando o autor pertence a um
setor acompanhante. A regra vive dentro do `notify()` (commit `6b036de`), não em
cada chamador: a versão anterior filtrava o autor só na lista de dono/cópia do
comentário, e o `notify_sector` logo abaixo notificava de volta quem tinha acabado
de escrever. Como todo caminho passa pelo `notify()`, o fan-out dos acompanhantes
já nasce coberto — mas isso precisa de teste explícito, porque é fácil alguém
"otimizar" o fan-out mais tarde criando `Notification` direto.

O `perform_create` do `TicketCommentViewSet` **não** é alterado — o silêncio no
comentário é a decisão, não um esquecimento. Um teste trava isso.

## 6. Menção → acompanhante — `tickets/serializer.py`

No `TicketSerializer`, após salvar as menções (create e update), para cada menção
**nova** (não presente antes): se o chamado mencionado tem `sector_id`, grava
`TicketWatcher(kind='sector', target_id=<setor do mencionado>, origin='mention',
source_ref=str(<pk do mencionado>))`, respeitando o princípio da seção anterior
(não sobrescreve `manual`).

Direção: **só uma**. O chamado 2 menciona o 1 → o setor do 1 acompanha o 2. O
inverso não acontece — quem foi mencionado não passa a acompanhar quem mencionou.

Desvincular a menção **não** remove o acompanhante.

## 7. Congelamento (decisão consciente)

O JWT traz o setor do usuário (`RemoteUser.sector`), **não** o departamento. Para
avaliar "esta pessoa pertence ao departamento acompanhante?" seria preciso um
claim novo no auth-server, invalidando tokens já emitidos e envolvendo o terceiro
repositório.

Optamos por evitar a pergunta: expandimos na escrita. O preço é que **setor criado
no departamento depois não passa a acompanhar chamados antigos**.

Saídas quando isso incomodar (nenhuma agora, e a linha de origem já as viabiliza):
comando de management que reexpande os departamentos gravados, ou reexpansão sob
demanda ao abrir o chamado.

## 8. Testes — `tickets/tests.py`

Escopo (o grupo que justifica o design):
1. Usuário do setor acompanhante **vê** o chamado na listagem e no detalhe.
2. Usuário do setor acompanhante **consegue comentar** (herda do escopo).
3. Linha `kind='department'` **não** dá acesso a ninguém sozinha.
4. Remover o acompanhante tira o acesso de volta.
5. Prova por mutação: removendo o `OR` novo de `ticket_visibility_q`, os testes 1 e 2 quebram.

Departamento:
6. Adicionar departamento grava a linha de origem + uma por setor ativo.
7. Auth-server fora do ar → **502**, e nenhuma linha gravada.
8. Departamento sem setor ativo → **400**, e nenhuma linha gravada.
9. Remover o departamento leva os setores dele e preserva o promovido a manual.

Sobreposição e menção:
10. Adicionar avulso um setor que veio do departamento o promove (`origin=manual`).
11. Expandir departamento não rebaixa um setor que já era manual.
12. Vincular menção grava acompanhante `origin=mention`; desvincular **não** remove.

Notificação:
13. Fechar/reabrir notifica os setores acompanhantes.
14. **Comentar não notifica acompanhante** (só dono, cópia e setor responsável).

Permissão:
15. Quem não é dono nem admin recebe 403 ao adicionar/remover acompanhante.

## Ordem de implementação

1. Modelo + migration + admin
2. `list_department_sectors` (com propagação de erro)
3. Rotas de adicionar/remover + leitura no detalhe
4. `ticket_visibility_q` + testes de escopo (com a prova por mutação)
5. Notificação de marcos
6. Menção → acompanhante
7. Suíte completa

## 9. Setor de quem abriu → acompanhante (HD-31)

Problema real observado: um colega do TI abre um chamado **para** a Manutenção, e
os demais colegas do TI deixam de ver esse chamado — `Ticket.sector_id` é sempre o
**destino**, e o setor de quem abriu não fica gravado em lugar nenhum.

Solução: reusar a mesma mecânica de acompanhante. Nova origem
`ORIGIN_REQUESTER = 'requester'` (rótulo "Setor de quem abriu"), incluída em
`ORIGIN_CHOICES` — migration só de metadados (`AlterField`), sem tocar em dado
existente.

No `perform_create` do `TicketViewSet`, depois do `_notify_sector` (que continua
avisando só o setor de **destino**), `_watch_requester_sector(ticket)` grava um
`TicketWatcher(kind='sector', origin='requester', source_ref='')` com o setor do
solicitante, reusando o `_upsert_sector_watcher` já existente (mesma normalização
de UUID do `add_watcher` — evita a linha órfã de UUID não-canônico).

Três guardas:

- **Sem setor no token** (`request.user.sector is None`): não grava nada, não
  quebra o `create`.
- **Setor do solicitante == setor de destino**: não grava. O setor já enxerga o
  chamado pelo caminho normal (`ticket.sector_id`); gravar aqui só duplicaria a
  linha sem trazer visibilidade nova.
- **UUID normalizado** antes do `get_or_create`, igual ao `add_watcher`.

**Sem notificação de inclusão neste caso.** O `add_watcher` manual notifica "Você
foi incluído no chamado #N" para o setor recém-incluído; aqui não — notificar o
setor inteiro a cada chamado aberto para outro setor viraria ruído constante. Os
colegas passam a **ver** o chamado (e recebem os marcos de fechado/reaberto como
qualquer acompanhante), sem notificação de entrada.

Testes em `tickets/tests.py::RequesterSectorWatcherTests`:
1. Chamado para outro setor grava o watcher `origin=requester` com o setor do
   solicitante.
2. Ponta a ponta (prova a demanda): colega do MESMO setor do solicitante, com
   outro `user_id`, passa a ver o chamado na listagem — provado por mutação
   (removendo a chamada a `_watch_requester_sector`, o teste falha).
3. Solicitante do mesmo setor do destino → nenhum watcher.
4. Solicitante sem setor no token → nenhum watcher, sem erro.
5. Criar chamado não notifica o setor do solicitante (só o destino), inspecionando
   as chamadas de `tickets.views.notify_sector`.
