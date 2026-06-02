from django.http import JsonResponse


def profile(request):
    # Diagnóstico temporário: mostra se o header chegou.
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    print('Authorization header:', auth_header[:40] or '(vazio)')
    print('request.user:', request.user, type(request.user).__name__)

    user = request.user
    if not getattr(user, 'is_authenticated', False):
        return JsonResponse({"detail": "Não autenticado"}, status=401)

    return JsonResponse({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.get_full_name(),
        "is_superuser": user.is_superuser,
        "permissions": user.permissions,
    })
