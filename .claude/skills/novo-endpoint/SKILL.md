---
name: novo-endpoint
description: Cria um endpoint REST novo seguindo o padrão do help-desk backend (Django + DRF). Use quando o usuário pedir para criar um novo recurso/CRUD/endpoint/model com API. Cobre model → serializer → view → url → admin e o registro no roteador.
---

# Novo endpoint — help-desk backend

Padrão do projeto: cada app expõe um `ModelViewSet` (CRUD de graça) registrado num
`DefaultRouter`. Usuários/setores vêm do **auth-server** (não há User local) — guardar só
UUIDs. Antes de começar, peça/decida: **app**, **nome do model** e **campos**.

> Convenções de nome: arquivos `serializer.py` e `filter.py` são **singular**. Classes do
> app levam o prefixo do app (ex.: `Ticket*`). Tabela: `db_table = 'db_<app>_<entidade>'`.

## 1. Model — `<app>/models.py`

```python
class TicketExemplo(models.Model):
    name = models.CharField(max_length=120)
    # UUIDs de usuário/setor vêm do auth-server; não usar FK para User local.
    user_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_exemplo'
        verbose_name = 'Ticket Exemplo'
        verbose_name_plural = 'Ticket Exemplos'

    def __str__(self):
        return self.name
```
Bases abstratas reaproveitáveis em `core/models.py`: `BaseNotification`
(`recipient_id`/`actor_id`/`actor_name`/`is_read`/`read_at`), `BaseView`
(`user_id`/`viewed_at`), `BaseLog` (`user_id`/`user_name`/`action`).

## 2. Serializer — `<app>/serializer.py`

```python
class TicketExemploSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketExemplo
        fields = "__all__"
```

## 3. ViewSet — `<app>/views.py`

```python
class TicketExemploViewSet(viewsets.ModelViewSet):
    """CRUD de ..."""
    queryset = TicketExemplo.objects.all()
    serializer_class = TicketExemploSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
```
**⚠️ Dono do recurso (`user_id`) — gap recorrente:** se o model tem `user_id` do dono,
o ViewSet **tem** que setá-lo a partir do token no `perform_create` **e** o serializer
**tem** que marcá-lo `read_only`. Sem isso: se `user_id` é NOT NULL a criação quebra
(`IntegrityError`); se é gravável, o cliente forja o dono (spoof).

```python
# views.py
def perform_create(self, serializer):
    serializer.save(user_id=self.request.user.id)

# serializer.py
read_only_fields = ["user_id", "created_at", "updated_at"]
```
(Cadastro compartilhado — ex.: `Enterprise` — não tem dono e dispensa isso.)

- Chamada ao auth-server (listar usuários/setor): passar o token do usuário com
  `self.request.user.auth_header` — ver `sector/services.py`, `users/services.py`.

## 4. URL — `<app>/urls.py`

Registrar no router **antes** da rota vazia `""` (senão o detalhe `/{pk}/` captura o nome):
```python
router.register("exemplos", TicketExemploViewSet, basename="ticket-exemplo")
```
Se o app é novo, garantir o include em `backend/api_urls.py`:
```python
path('<app>/', include("<app>.urls")),
```

## 5. Admin — `<app>/admin.py` (NÃO ESQUEÇA — gap recorrente)

Registrar **todos** os models do app, inclusive os lookups. Apps já ficaram com o
`admin.py` vazio (`# Register your models here.`) por esquecimento — sempre conferir.

```python
@admin.register(TicketExemplo)
class TicketExemploAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name',)
```

## 6. Filtro (opcional) — `<app>/filter.py`

Se for filtrar, prefira um `FilterSet` dedicado em `filter.py` + `filterset_class` no
viewset (padrão de `tickets`/`machines`) em vez de `filterset_fields` inline na view.

```python
class TicketExemploFilter(django_filters.FilterSet):
    class Meta:
        model = TicketExemplo
        fields = {"user_id": ["exact"], "created_at": ["date", "gte", "lte"]}
```
E no viewset: `filterset_class = TicketExemploFilter`.

## 7. Migrar

`python manage.py makemigrations && python manage.py migrate`. Em fase de
desenvolvimento com mudança de schema ampla, use a skill **/reseta**.

## Checklist (pegadinhas comuns)

- [ ] Model com `db_table = 'db_<app>_<entidade>'` e classe com prefixo do app.
- [ ] Tem `user_id` de dono? → `perform_create` seta do token **e** serializer marca `read_only`.
- [ ] **Admin**: todos os models registrados (não deixar o `admin.py` vazio).
- [ ] Rotas nomeadas/lookups registradas **antes** da rota `""`.
- [ ] App novo incluído no `backend/api_urls.py`.
- [ ] Filtro (se houver) via `filter.py` + `filterset_class`.

## Conferir

`python manage.py check` limpo; testar a rota no router (`GET /<app>/exemplos/`).
