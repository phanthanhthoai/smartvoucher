from django.contrib.auth.models import User


def register_user(username, email, password):
    if User.objects.filter(username=username).exists():
        return None, "Username already exists"

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )
    return user, None
