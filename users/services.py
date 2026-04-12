from django.contrib.auth import get_user_model

from vouchers.services.distribution import assign_welcome_vouchers_to_user


def register_user(username, email, password):
    User = get_user_model()

    if User.objects.filter(username=username).exists():
        return None, "Username already exists"
    
    if User.objects.filter(email=email).exists():
        return None, "Email này đã được sử dụng cho một tài khoản khác."

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    assign_welcome_vouchers_to_user(user)

    return user, None


def staff_user(username, email, password):
    User = get_user_model()

   # 1. Kiểm tra Username
    if User.objects.filter(username=username).exists():
        return None, "Username này đã tồn tại."

    # 2. Kiểm tra Email (THÊM MỚI VÀO ĐÂY)
    if User.objects.filter(email=email).exists():
        return None, "Email này đã được sử dụng cho một tài khoản khác."

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        role='staff',
    )

    return user, None