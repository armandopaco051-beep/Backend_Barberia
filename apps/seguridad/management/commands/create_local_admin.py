from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.seguridad.models import Rol, Usuario


LOCAL_ADMIN_EMAIL = 'renato@gmail.com'
LOCAL_ADMIN_PASSWORD = '12345678'
LOCAL_ADMIN_NAME = 'Renato'
LOCAL_ADMIN_LAST_NAME = 'Local'
LOCAL_ADMIN_PHONE = '70000000'
LOCAL_ADMIN_CODE = 'LOCALADMIN'
PRIMARY_ADMIN_ROLE_NAME = 'administrador'
ADMIN_ROLE_ALIASES = {'administrador', 'admin'}


class Command(BaseCommand):
    help = 'Create or update the local admin user used for development testing.'

    def handle(self, *args, **options):
        with transaction.atomic():
            admin_role, role_created = self._get_or_create_admin_role()
            usuario, created, deduplicated = self._upsert_local_admin(admin_role)

        if role_created:
            self.stdout.write(self.style.SUCCESS(f'Se creo el rol administrativo "{admin_role.nombre}".'))
        else:
            self.stdout.write(f'Se reutilizo el rol administrativo "{admin_role.nombre}" (id={admin_role.id}).')

        for old_email, new_email, codigo in deduplicated:
            self.stdout.write(
                self.style.WARNING(
                    f'Se ajusto el correo duplicado de {codigo}: "{old_email}" -> "{new_email}".'
                )
            )

        action = 'creado' if created else 'actualizado'
        self.stdout.write(self.style.SUCCESS(f'Usuario local admin {action}: {usuario.codigo} <{usuario.correo}>'))
        self.stdout.write(f'Rol asignado: {usuario.id_rol.nombre}')
        self.stdout.write('Credenciales locales:')
        self.stdout.write(f'  Correo: {LOCAL_ADMIN_EMAIL}')
        self.stdout.write(f'  Password: {LOCAL_ADMIN_PASSWORD}')

    def _get_or_create_admin_role(self):
        admin_role = Rol.objects.filter(nombre__iexact=PRIMARY_ADMIN_ROLE_NAME).first()
        if admin_role:
            return admin_role, False

        alias_role = next(
            (role for role in Rol.objects.all().order_by('id') if role.nombre.strip().lower() in ADMIN_ROLE_ALIASES),
            None,
        )
        if alias_role and alias_role.nombre.strip().lower() == PRIMARY_ADMIN_ROLE_NAME:
            return alias_role, False

        role = Rol.objects.create(nombre=PRIMARY_ADMIN_ROLE_NAME)
        return role, True

    def _upsert_local_admin(self, admin_role):
        usuarios = list(
            Usuario.objects.select_related('id_rol')
            .filter(correo__iexact=LOCAL_ADMIN_EMAIL)
            .order_by('codigo')
        )
        usuarios.sort(key=lambda usuario: (usuario.id_rol.nombre.strip().lower() != PRIMARY_ADMIN_ROLE_NAME, usuario.codigo))

        primary = usuarios[0] if usuarios else None
        duplicates = usuarios[1:]
        deduplicated = []

        for duplicate in duplicates:
            old_email = duplicate.correo
            duplicate.correo = self._build_unique_placeholder_email(duplicate.codigo)
            duplicate.save(update_fields=['correo'])
            deduplicated.append((old_email, duplicate.correo, duplicate.codigo))

        created = primary is None
        if created:
            primary = Usuario(codigo=self._build_unique_code(LOCAL_ADMIN_CODE))

        primary.nombre = LOCAL_ADMIN_NAME
        if created or not primary.apellido.strip():
            primary.apellido = LOCAL_ADMIN_LAST_NAME
        if created or not primary.telefono.isdigit() or len(primary.telefono) > 10:
            primary.telefono = LOCAL_ADMIN_PHONE
        primary.correo = LOCAL_ADMIN_EMAIL
        primary.id_rol = admin_role
        primary.password = make_password(LOCAL_ADMIN_PASSWORD)
        primary.intentos_fallidos = 0
        primary.bloqueado_hasta = None
        primary.codigo_recuperacion = None
        primary.codigo_recuperacion_expira = None

        if created and not primary.especialidad:
            primary.especialidad = None

        primary.save()
        return primary, created, deduplicated

    def _build_unique_code(self, base_code):
        if not Usuario.objects.filter(codigo=base_code).exists():
            return base_code

        suffix = 1
        while True:
            candidate = f'{base_code}{suffix:02d}'
            if not Usuario.objects.filter(codigo=candidate).exists():
                return candidate
            suffix += 1

    def _build_unique_placeholder_email(self, codigo):
        base = f'renato-duplicate-{codigo}'.lower()
        candidate = f'{base}@local.invalid'
        suffix = 1

        while Usuario.objects.filter(correo__iexact=candidate).exists():
            candidate = f'{base}-{suffix}@local.invalid'
            suffix += 1

        return candidate
