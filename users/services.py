from django.contrib.auth import get_user_model

from vouchers.services.distribution import assign_welcome_vouchers_to_user


def register_user(username, email, password):
    User = get_user_model()

    if User.objects.filter(username=username).exists():
        return None, "Username already exists"

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    assign_welcome_vouchers_to_user(user)

    return user, None
