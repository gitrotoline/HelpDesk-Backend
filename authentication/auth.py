"""RemoteUser stub populado por JWT (claims slim) + cache Redis (extras).

Arquitetura: o auth-server externo emite um JWT curto (~10 min) com só o
essencial pra autenticação (`sub`, `permissions`, `setor`, `is_superuser`,
`is_staff`, `exp`). Dados de exibição (nome, email, cpf, sap_code, escala,
groups) vêm do cache Redis com fallback HTTP — ver `usuario.services.fetch_user`.

O middleware passa `claims` (do JWT) e `extra` (do cache). Claims do JWT
prevalecem quando ambos estão presentes — JWT é a fonte de verdade pra auth.
"""


class _Sector:
    """Setor do usuário (vindo do JWT). Expõe `id` e `name`."""
    def __init__(self, id=None, name=None):
        self.id = id
        self.name = name

    def __str__(self):
        return self.name or ''

class _Schedule:
    def __init__(self, data):
        if isinstance(data, dict):
            self.id = data.get('id')
            self.nome = data.get('name') or data.get('nome')
        else:
            self.id = None
            self.nome = data

    def __str__(self):
        return self.nome or ''

class _DepartamentoStub:
    def __init__(self, data):
        if isinstance(data, dict):
            self.id = data.get('id')
            self.nome = data.get('name') or data.get('nome')
        else:
            self.id = None
            self.nome = data

    def __str__(self):
        return self.nome or ''


class _GroupStub:
    def __init__(self, data):
        if isinstance(data, dict):
            self.id = data.get('id')
            self.name = data.get('name') or data.get('nome')
        else:
            self.id = None
            self.name = data

    def __str__(self):
        return self.name or ''


class _GroupQS:
    def __init__(self, items):
        self._items = list(items)

    def exists(self):
        return bool(self._items)

    def __iter__(self):
        return iter(self._items)

    def count(self):
        return len(self._items)


class _GroupsManager:
    def __init__(self, raw):
        self._items = [_GroupStub(x) for x in (raw or [])]

    def filter(self, name=None, name__in=None, **kwargs):
        result = self._items
        if name is not None:
            result = [g for g in result if g.name == name]
        if name__in is not None:
            allowed = set(name__in)
            result = [g for g in result if g.name in allowed]
        return _GroupQS(result)

    def all(self):
        return _GroupQS(self._items)

    def values_list(self, *args, flat=False):
        if flat:
            return [g.name for g in self._items]
        return [(g.name,) for g in self._items]


class RemoteUser:
    is_authenticated = True
    is_anonymous = False

    def __init__(self, claims, extra=None, access_token=None):
        merged = {**(extra or {}), **claims}

        # Access token validado (o mesmo Bearer que o front enviou). Guardado
        # aqui para repassar nas chamadas em nome do usuário ao auth-server.
        self.access_token = access_token

        self.id = merged.get('user_id') or merged.get('sub')
        self.username = merged.get('username') or ''
        self.email = merged.get('email') or ''
        self.cpf = merged.get('cpf')
        self.sap_code = merged.get('sap_code')
        self.email_verified = merged.get('email_verified', False)
        self.phone = merged.get('phone') or ''
        self.phone_verified = merged.get('phone_verified', False)
        self.first_name = merged.get('first_name', '')
        self.last_name = merged.get('last_name', '')

        self.is_active = merged.get('is_active', True)
        self.is_staff = merged.get('is_staff', False)
        self.is_superuser = merged.get('is_superuser', False)

        self.departamento = _DepartamentoStub(merged['department']) if merged.get('department') else None
        # Setor: aceita tanto um objeto {"id","name"} quanto os claims planos
        # sector_id / sector_name. None se o token não trouxer setor.
        _sector = merged.get('sector')
        if isinstance(_sector, dict):
            self.sector = _Sector(_sector.get('id'), _sector.get('name') or _sector.get('nome'))
        elif merged.get('sector_id'):
            self.sector = _Sector(merged.get('sector_id'), merged.get('sector_name'))
        else:
            self.sector = None
        self.escala = _Schedule(merged['schedule']) if merged.get('schedule') else None
        self.groups = _GroupsManager(merged.get('groups', []))
        self._permissions = set(merged.get('permissions', []))

    @property
    def permissions(self):
        return sorted(self._permissions)

    @property
    def auth_header(self):
        """Header pronto p/ repassar o token do usuário ao auth-server."""
        return f'Bearer {self.access_token}' if self.access_token else None

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.username}"

    def get_username(self):
        return self.username

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def has_perm(self, perm, obj=None):
        if self.is_superuser:
            return True
        return perm in self._permissions

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(p, obj) for p in perm_list)

    def has_module_perms(self, app_label):
        if self.is_superuser:
            return True
        return any(p.startswith(f'{app_label}.') for p in self._permissions)
