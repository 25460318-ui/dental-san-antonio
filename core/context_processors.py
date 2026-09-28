from .models import ClinicInfo


def clinic_info(request):
    return {"clinic_info": ClinicInfo.objects.first()}
