from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Voucher
from .serializers import CreateVoucherSerializer, CheckVoucherSerializer
from .services import generate_voucher_code, check_voucher, send_voucher_email, send_voucher_sms


class CreateVoucherAPI(APIView):
    def post(self, request):
        serializer = CreateVoucherSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        voucher = serializer.save(
            code=generate_voucher_code()
        )

        return Response(
            {
                "message": "Voucher created successfully",
                "voucher_code": voucher.code
            },
            status=status.HTTP_201_CREATED
        )


class CheckVoucherAPI(APIView):
    def post(self, request):
        serializer = CheckVoucherSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        result = check_voucher(
            data["voucher_code"],
            data["order_total"],
            user=request.user 
        )

        if not result["valid"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class SendVoucherEmailAPI(APIView):
    def post(self, request):
        email = request.data.get("email")
        voucher_code = request.data.get("voucher_code")

        send_voucher_email(email, voucher_code)

        return Response({"message": "Email sent"}, status=status.HTTP_200_OK)


class SendVoucherSMSAPI(APIView):
    def post(self, request):
        phone = request.data.get("phone")
        voucher_code = request.data.get("voucher_code")

        send_voucher_sms(phone, voucher_code)

        return Response({"message": "SMS sent"})
