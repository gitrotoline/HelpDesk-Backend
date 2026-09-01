---
name: seed
description: Popula o banco do help-desk backend com os dados de referência. Use quando o usuário pedir para rodar os seeds / popular dados base (status, prioridades e tipos de ticket; países; estados e cidades) sem recriar o banco. Para resetar o banco do zero, use a skill /reseta.
---

# Seeds — help-desk backend

Rodar **de `backend/`** com o virtualenv ativo. Os comandos são **idempotentes**
(`get_or_create`), então podem rodar várias vezes sem duplicar.

**O caminho curto — roda tudo, na ordem certa:**

```powershell
python manage.py seed_all              # tudo
python manage.py seed_all --skip-geo   # sem países/estados/cidades (a parte demorada)
```

Os comandos individuais (em `core/management/commands/`), caso queira rodar um só:

```powershell
python manage.py ticket_refs       # situações, prioridades e tipos de ticket
python manage.py enterprises_refs  # referências de empresa
python manage.py machine_refs      # referências de máquina
python manage.py country           # países
python manage.py state_and_city    # estados e cidades (depende de country)
```

O `ticket_refs` também ATUALIZA o que já existe: grau e destaque da prioridade,
e as flags da situação (padrão / final / início de atendimento). Sem uma situação
padrão cadastrada o sistema não abre chamado — a criação resolve a situação
inicial pelo cadastro e devolve 400 quando não há candidata.

(*) Os models de referência hoje têm prefixo `Ticket*` (`TicketStatus`,
`TicketPriority`, `TicketType`) — o comando `ticket_refs` semeia esses três.

## Ordem

`state_and_city` depende de `country` (estados referenciam países) → rodar **`country`
antes** de `state_and_city`. `ticket_refs` é independente, pode rodar em qualquer ordem.

Ordem segura: `ticket_refs` → `country` → `state_and_city`.

## Esperado

- `ticket_refs`: 3 status (Aberto/Em andamento/Fechado), 4 prioridades, 3 tipos.
- `country`: ~199 países.
- `state_and_city`: ~111 estados, ~286 cidades.

## Rodar tudo de uma vez

```powershell
python manage.py ticket_refs; python manage.py country; python manage.py state_and_city
```
