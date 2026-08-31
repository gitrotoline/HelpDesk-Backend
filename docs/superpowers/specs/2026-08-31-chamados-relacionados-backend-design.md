# Design — Chamados relacionados no detalhe do ticket (backend)

Data: 2026-08-31
App: `tickets` (backend Django + DRF)
Par no frontend: `frontend/docs/superpowers/specs/2026-08-31-chamados-relacionados-frontend-design.md`

## Objetivo

Hoje o `TicketSerializer` devolve `mentions` como uma lista crua de pks. A tela de
detalhe do frontend só consegue mostrar `#12`, `#18` — o usuário não sabe do que
se trata e precisa abrir cada um para descobrir.

Este design expõe, **só no detalhe** (`GET /tickets/{id}/`), o resumo dos chamados
relacionados nas duas direções, com filtro de visibilidade.

## Decisões tomadas

- **Duas direções**: `mentions_detail` (este chamado menciona) e
  `mentioned_in_detail` (este chamado é mencionado por). A M2M já é
  `symmetrical=False` com `related_name='mentioned_in'` — a direção inversa
  existe no banco e nunca foi exposta.
- **Resumo, não conteúdo**: cada item traz cabeçalho + `comments_count`. As
  mensagens são buscadas sob demanda pelo frontend em
  `GET /tickets/comments/?ticket=<id>`, que **já** filtra por visibilidade no
  `TicketCommentViewSet`. Nada de aninhar thread no payload do ticket.
- **Filtro de visibilidade obrigatório** (ver "Segurança").
- **Só no retrieve**: serializer dedicado, para a listagem não pagar o custo.
- `mentions` (lista de pks) **continua existindo** — é o campo de escrita usado
  pelo formulário do frontend. Não mexer.

## Segurança — o ponto central deste design

As menções podem apontar para chamados que o usuário não pode ver
(`ticket_visibility_q`, em `tickets/scope.py`). Hoje isso vaza apenas o número.
Ao devolver assunto, solicitante e setor, a menção viraria uma porta lateral em
volta do escopo.

Portanto **as duas listas são filtradas por `ticket_visibility_q(request.user)`**.
Um chamado fora do escopo simplesmente não aparece na lista — sem placeholder,
sem "#18 (sem acesso)", que também é informação.

## Fora de escopo (YAGNI)

- Editar as relações por aqui (a escrita continua pelo campo `mentions`).
- Expor os relacionados na listagem (`GET /tickets/`).
- Aninhar comentários/anexos dos relacionados no payload.
- Grafo transitivo (relacionado do relacionado).

## 1. Serializer do resumo — `tickets/serializer.py`

```python
class TicketRelatedSerializer(serializers.ModelSerializer):
    """Resumo de um chamado relacionado — cabeçalho, sem descrição nem thread."""
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
```

Sem `description`: o card mostra cabeçalho, e ao expandir o frontend busca a
thread. Se a descrição se mostrar necessária no expandido, ela entra numa
iteração seguinte — não vale carregar TextField de N chamados por padrão.

## 2. Serializer de detalhe — `tickets/serializer.py`

```python
class TicketDetailSerializer(TicketSerializer):
    """Igual ao TicketSerializer + os relacionados. Usado só no retrieve."""
    mentions_detail = serializers.SerializerMethodField()
    mentioned_in_detail = serializers.SerializerMethodField()

    def _related(self, manager):
        user = self.context['request'].user
        qs = (
            manager.filter(ticket_visibility_q(user))
            .select_related('status', 'priority')
            .annotate(comments_count=Count('comments', distinct=True))
            .distinct()
            .order_by('-created_at')
        )
        return TicketRelatedSerializer(qs, many=True).data

    def get_mentions_detail(self, obj):
        return self._related(obj.mentions)

    def get_mentioned_in_detail(self, obj):
        return self._related(obj.mentioned_in)
```

`distinct()` pelo mesmo motivo do `TicketViewSet.get_queryset`: o `Q` de
visibilidade faz JOIN com `recipients` e pode repetir linhas.

## 3. View — `tickets/views.py`

```python
def get_serializer_class(self):
    # Os relacionados custam 2 queries por objeto; na listagem isso seria N+1.
    if self.action == 'retrieve':
        return TicketDetailSerializer
    return TicketSerializer
```

As actions `close`/`reopen` devolvem `self.get_serializer(ticket).data` — com
`self.action` valendo `'close'`/`'reopen'`, elas continuam usando o
`TicketSerializer` normal. O frontend faz `router.refresh()` depois dessas
ações, então o detalhe é recarregado de qualquer forma.

## 4. Contrato para o frontend

`GET /tickets/{id}/` passa a incluir:

```jsonc
{
  "id": 42,
  "mentions": [12, 18],            // inalterado (escrita)
  "mentions_detail": [
    {
      "id": 18,
      "subject": "Troca do toner",
      "status_name": "Fechado",
      "priority_name": "Baixa",
      "user_name": "Maria",
      "sector_name": "TI",
      "created_at": "2026-06-25T09:12:00Z",
      "closed_at": "2026-06-25T14:00:00Z",
      "comments_count": 2
    }
  ],
  "mentioned_in_detail": [ /* mesmo formato */ ]
}
```

As duas listas podem ser menores que `mentions` (itens fora do escopo saem) ou
vazias. O frontend não deve inferir contagem a partir de `mentions`.

## 5. Testes — `tickets/tests.py`

1. Detalhe devolve `mentions_detail` com assunto e `comments_count` correto.
2. `mentioned_in_detail` traz o chamado que menciona este (direção inversa).
3. **Escopo**: chamado mencionado que o usuário não pode ver **não aparece** em
   nenhuma das duas listas — e o `mentions` cru continua trazendo o pk.
4. Admin vê todos os relacionados.
5. Listagem (`GET /tickets/`) **não** traz os campos novos.

O teste 3 é o que justifica o design; se algum dia alguém simplificar o
`_related` removendo o filtro, é ele que quebra.

## Ordem de implementação

1. `TicketRelatedSerializer` + `TicketDetailSerializer`
2. `get_serializer_class` no `TicketViewSet`
3. Testes (rodar `python manage.py test tickets`)
