from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from vouchers.models import UserVoucher, Voucher, VoucherDistributionPlan
from vouchers.services.notification import send_voucher_email
from vouchers.services.rule_engine import check_user_condition


def _filter_users_by_rule(users, rule):
    eligible = []
    for user in users:
        if check_user_condition(user, rule):
            eligible.append(user)
    return eligible


def assign_voucher_to_user(user, voucher):
    _, created = UserVoucher.objects.get_or_create(user=user, voucher=voucher)
    if created:
        send_voucher_email(user, voucher)
    return created


def distribute_voucher(voucher, users):
    rule = voucher.rule
    eligible_users = _filter_users_by_rule(users, rule)

    created = 0
    skipped = 0
    for user in eligible_users:
        was_created = assign_voucher_to_user(user, voucher)
        if was_created:
            created += 1
        else:
            skipped += 1

    return created, skipped, len(eligible_users)


def get_target_users(user_ids=None):
    User = get_user_model()
    if user_ids:
        return User.objects.filter(id__in=user_ids)
    return User.objects.all()


def assign_welcome_vouchers_to_user(user):
    """
    Assign active welcome vouchers to a newly registered user if eligible.
    """
    vouchers = Voucher.objects.filter(
        event_type="welcome",
        release_date__lte=timezone.now(),
        expiry_date__gte=timezone.now()
    ).order_by("id")

    assigned = 0
    skipped = 0

    for voucher in vouchers:
        try:
            rule = voucher.rule
        except ObjectDoesNotExist:
            skipped += 1
            continue

        if not check_user_condition(user, rule):
            skipped += 1
            continue

        created = assign_voucher_to_user(user, voucher)
        if created:
            assigned += 1
        else:
            skipped += 1

    return assigned, skipped


def create_distribution_plan(voucher, user_ids=None):
    return VoucherDistributionPlan.objects.create(
        voucher=voucher,
        user_ids=user_ids or None
    )


def execute_distribution_plan(plan):
    voucher = plan.voucher
    now = timezone.now()

    if voucher.expiry_date <= now:
        plan.status = VoucherDistributionPlan.STATUS_SKIPPED_EXPIRED
        plan.distributed_at = now
        plan.save(update_fields=["status", "distributed_at"])
        return 0, 0, 0

    users = get_target_users(user_ids=plan.user_ids)
    created, skipped, eligible = distribute_voucher(voucher, users)

    plan.status = VoucherDistributionPlan.STATUS_COMPLETED
    plan.distributed_at = now
    plan.save(update_fields=["status", "distributed_at"])
    return created, skipped, eligible


def process_due_distribution_plans():
    plans = VoucherDistributionPlan.objects.select_related("voucher").filter(
        status=VoucherDistributionPlan.STATUS_PENDING,
        voucher__release_date__lte=timezone.now()
    )

    processed = 0
    for plan in plans:
        execute_distribution_plan(plan)
        processed += 1

    return processed
