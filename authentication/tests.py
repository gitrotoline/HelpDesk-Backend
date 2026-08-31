from django.test import TestCase

# Create your tests here.


from django.test import TestCase

from .auth import RemoteUser


class RemoteUserSectorShapeTests(TestCase):
    """O auth-server manda o NOME do setor em `sector` (string) e o id em
    `sector_id` — ver UserSerializer de lá. Antes disto o RemoteUser procurava o
    nome em `sector_name`, que não existe naquele payload: o id vinha certo (a
    visibilidade funcionava) e o nome vinha vazio, então a tela mostrava o
    acompanhante sem o nome do setor."""

    CLAIMS = {'user_id': '11111111-1111-1111-1111-111111111111'}

    def test_reads_name_from_flat_payload_of_auth_server(self):
        user = RemoteUser(self.CLAIMS, extra={
            'sector': 'TI',
            'sector_id': '22222222-2222-2222-2222-222222222222',
        })
        self.assertEqual(str(user.sector.id), '22222222-2222-2222-2222-222222222222')
        self.assertEqual(user.sector.name, 'TI')

    def test_still_reads_object_shape(self):
        # Forma {"id","name"} (usada pelos testes e por tokens que a tragam).
        user = RemoteUser(self.CLAIMS, extra={
            'sector': {'id': '33333333-3333-3333-3333-333333333333', 'name': 'Manutencao'},
        })
        self.assertEqual(user.sector.name, 'Manutencao')

    def test_no_sector_stays_none(self):
        self.assertIsNone(RemoteUser(self.CLAIMS).sector)
