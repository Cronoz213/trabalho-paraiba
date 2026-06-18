from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria o superusuario padrao admin/Admin@2026 se ainda nao existir."

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username="admin").exists():
            self.stdout.write("Superuser 'admin' ja existe.")
            return
        User.objects.create_superuser("admin", "admin@projeto.com", "Admin@2026")
        self.stdout.write(self.style.SUCCESS("Superuser criado: admin / Admin@2026"))
