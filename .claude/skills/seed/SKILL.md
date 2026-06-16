---
name: seed
description: Popula o banco do help-desk backend com os dados de referência. Use quando o usuário pedir para rodar os seeds / popular dados base (status, prioridades e tipos de ticket; países; estados e cidades) sem recriar o banco. Para resetar o banco do zero, use a skill /reseta.
---

# Seeds — help-desk backend

Rodar **de `backend/`** com o virtualenv ativo. Os comandos são **idempotentes**
(`get_or_create`), então podem rodar várias vezes sem duplicar.

Os três comandos de seed do projeto (em `core/management/commands/`):

```powershell
python manage.py ticket_refs       # StatusOfTicket(*), prioridades e tipos de ticket
python manage.py country           # países
python manage.py state_and_city    # estados e cidades
```

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
