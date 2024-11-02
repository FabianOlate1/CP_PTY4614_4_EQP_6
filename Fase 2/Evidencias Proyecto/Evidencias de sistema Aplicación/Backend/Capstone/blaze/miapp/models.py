from django.db import models
from django.contrib.auth.models import User, Group, AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.validators import RegexValidator
from datetime import datetime
from django.db.models import Sum
from fcm_django.models import FCMDevice


import re


# Usuarios


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    is_superadmin = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=30)
    apellido = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre', 'apellido']

    objects = CustomUserManager()

    def __str__(self):
        return self.email

    def has_module_perms(self, app_label):
        return True


# Perfiles de ingreso

class Perfil(models.Model):
    USER_ROLES = (
        ('cliente', 'Cliente'),
        ('dueño', 'Dueño'),
        ('administrador', 'Administrador'),
        ('trabajador', 'Trabajador'),
        ('supervisor', 'Supervisor'),
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rol = models.CharField(
        max_length=20, choices=USER_ROLES, default='cliente')

    def __str__(self):
        return f"{self.user.email} - {self.rol}"


# Asignacion de grupos segun rol

@receiver(post_save, sender=Perfil)
def asignar_grupo_por_rol(sender, instance, created, **kwargs):
    if created:
        group = None
        if instance.rol == 'cliente':
            group = Group.objects.get(name='Clientes')
        elif instance.rol == 'administrador':
            group = Group.objects.get(name='Administradores')
        elif instance.rol == 'trabajador':
            group = Group.objects.get(name='Trabajadores')
        elif instance.rol == 'supervisor':
            group = Group.objects.get(name='Supervisores')

        if group:
            instance.user.groups.add(group)


# Crear el perfil

@receiver(post_save, sender=CustomUser)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.get_or_create(user=instance)


@receiver(post_save, sender=CustomUser)
def guardar_perfil_usuario(sender, instance, **kwargs):
    try:
        perfil = Perfil.objects.get(user=instance)
        print("El perfil ya existe y no se creará uno duplicado.")
    except Perfil.DoesNotExist:
        print("El perfil no existe y será creado.")
        perfil = Perfil(user=instance)
        perfil.save()


class Dueño(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    rut_validator = RegexValidator(
        regex=r'^\d{7,8}-[0-9kK]{1}$',
        message="El RUT debe tener el formato 12345678-9."
    )

    rut = models.CharField(max_length=10, unique=True,
                           validators=[rut_validator])
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    telefono = models.CharField(max_length=15)
    direccion = models.TextField()
    perfil = models.ForeignKey(
        Perfil, on_delete=models.CASCADE, related_name='dueño')
    rol = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.rut}) - {self.rol}"


class Vehiculo(models.Model):
    patente = models.CharField(max_length=10, unique=True)

    def clean(self):
        # Validación para año
        if self.año < 1886 or self.año > datetime.now().year:
            raise ValidationError(_('Año inválido para el vehículo.'))

        # Validación para patente
        regex_patente = r'^([A-Z]{2}\d{4}|[A-Z]{4}\d{2})$'
        if not re.match(regex_patente, self.patente):
            raise ValidationError(f"La patente {
                                  self.patente} no es válida. Debe seguir el formato AB1234 o ABCD12.")

        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        super(Vehiculo, self).save(*args, **kwargs)

    marca = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100)
    año = models.IntegerField()

    color = models.CharField(max_length=50)
    kilometraje = models.IntegerField()
    tipo_combustible = models.CharField(max_length=50, choices=[
        ('bencina', 'Bencina'),
        ('diesel', 'Diésel'),
    ])
    fecha_ultima_revision = models.DateField()
    estado_vehiculo = models.CharField(max_length=100, choices=[
        ('disponible', 'Disponible'),
        ('en_reparacion', 'En Reparación'),
        ('no_disponible', 'No Disponible'),
    ])
    dueño = models.ForeignKey(
        Dueño, on_delete=models.CASCADE, related_name='vehiculos')

    class Meta:
        unique_together = ('patente', 'dueño')

    def __str__(self):
        return f"{self.marca} {self.modelo} ({self.patente}) - Estado: {self.estado_vehiculo}"


class Servicio(models.Model):
    id_servicio = models.AutoField(primary_key=True)
    nombre_servicio = models.CharField(max_length=100)
    descripcion = models.TextField()
    costo = models.DecimalField(max_digits=10, decimal_places=2)
    duracion_estimada = models.IntegerField()
    garantia = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre_servicio


class Administrador(models.Model):
    rut = models.CharField(max_length=12, primary_key=True, unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    telefono = models.CharField(max_length=15)
    email = models.EmailField()
    direccion = models.TextField()
    DISPONIBILIDAD_OPCIONES = [
        ('disponible', 'Disponible'),
        ('ocupado', 'Ocupado'),
        ('en_vacaciones', 'En Vacaciones'),
    ]
    ESTADO_OPCIONES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('suspendido', 'Suspendido'),
    ]
    ASIGNACION_OPCIONES = [
        ('mecanico', 'Mecánico'),
        ('pintor', 'Pintor'),
        ('electrico', 'Eléctrico'),
        ('jefe_taller', 'Jefe de Taller'),
    ]
    disponibilidad = models.CharField(
        max_length=50, choices=DISPONIBILIDAD_OPCIONES)
    estado = models.CharField(max_length=20, choices=ESTADO_OPCIONES)
    asignacion = models.CharField(max_length=50, choices=ASIGNACION_OPCIONES)
    perfil = models.ForeignKey(
        Perfil, on_delete=models.CASCADE, related_name='administrador')
    rol = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.rol}"


class Supervisor(models.Model):
    rut = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    telefono = models.CharField(max_length=15)
    email = models.EmailField()
    direccion = models.TextField()
    DISPONIBILIDAD_OPCIONES = [
        ('disponible', 'Disponible'),
        ('ocupado', 'Ocupado'),
        ('en_vacaciones', 'En Vacaciones'),
    ]
    ESTADO_OPCIONES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('suspendido', 'Suspendido'),
    ]
    ASIGNACION_OPCIONES = [
        ('mecanico', 'Mecánico'),
        ('pintor', 'Pintor'),
        ('electrico', 'Eléctrico'),
        ('jefe_taller', 'Jefe de Taller'),
    ]
    disponibilidad = models.CharField(
        max_length=50, choices=DISPONIBILIDAD_OPCIONES)
    estado = models.CharField(max_length=20, choices=ESTADO_OPCIONES)
    asignacion = models.CharField(max_length=50, choices=ASIGNACION_OPCIONES)
    perfil = models.ForeignKey(
        Perfil, on_delete=models.CASCADE, related_name='supervisor')
    rol = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.rol}"


class Trabajador(models.Model):
    id_trabajador = models.AutoField(primary_key=True)
    rut = models.CharField(max_length=12)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    telefono = models.CharField(max_length=15)
    email = models.EmailField()
    direccion = models.TextField()
    DISPONIBILIDAD_OPCIONES = [
        ('disponible', 'Disponible'),
        ('ocupado', 'Ocupado'),
        ('en_vacaciones', 'En Vacaciones'),
    ]
    ESTADO_OPCIONES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('suspendido', 'Suspendido'),
    ]
    ASIGNACION_OPCIONES = [
        ('mecanico', 'Mecánico'),
        ('pintor', 'Pintor'),
        ('electrico', 'Eléctrico'),
        ('jefe_taller', 'Jefe de Taller'),
    ]
    disponibilidad = models.CharField(
        max_length=50, choices=DISPONIBILIDAD_OPCIONES)
    estado = models.CharField(max_length=20, choices=ESTADO_OPCIONES)
    asignacion = models.CharField(max_length=50, choices=ASIGNACION_OPCIONES)
    perfil = models.ForeignKey(
        Perfil, on_delete=models.CASCADE, related_name='trabajador')
    rol = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.rol}"


class Notificacion(models.Model):
    mensaje = models.TextField()
    fecha_envio = models.DateTimeField(auto_now_add=True)

    ESTADO_OPCIONES = [
        ('enviada', 'Enviada'),
        ('pendiente', 'Pendiente'),
        ('vista', 'Vista'),
        ('cancelada', 'Cancelada'),
    ]

    estado = models.CharField(max_length=50, choices=ESTADO_OPCIONES)
    proceso = models.ForeignKey(
        'Proceso', on_delete=models.CASCADE, related_name='notificaciones_proceso')
    dispositivo_token = models.CharField(
        max_length=255, default='', null=False)

    def __str__(self):
        return f"Notificación {self.id} - Estado: {self.estado} - Mensaje: {self.mensaje}"

    def __str__(self):
        return f"Notificación {self.id} - Estado: {self.estado} - {self.fecha.strftime('%Y-%m-%d %H:%M')}"


class Proceso(models.Model):
    FASE_CHOICES = [
        ('iniciado', 'Iniciado'),
        ('en_progreso', 'En Progreso'),
        ('completado', 'Completado'),
        ('en_espera', 'En Espera'),
        ('cancelado', 'Cancelado'),
    ]
    fase_proceso = models.CharField(max_length=100, choices=FASE_CHOICES)
    descripcion = models.TextField()
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(null=True, blank=True)

    ESTADO_PROCESO_OPCIONES = [
        ('iniciado', 'Iniciado'),
        ('en_progreso', 'En Progreso'),
        ('completado', 'Completado'),
        ('pendiente', 'Pendiente'),
    ]

    PRIORIDAD_OPCIONES = [
        ('alta', 'Alta'),
        ('media', 'Media'),
        ('baja', 'Baja'),
    ]
    estado_proceso = models.CharField(
        max_length=100, choices=ESTADO_PROCESO_OPCIONES)
    prioridad = models.CharField(max_length=50, choices=PRIORIDAD_OPCIONES)
    comentarios = models.TextField(null=True, blank=True)
    trabajador = models.ForeignKey(Trabajador, on_delete=models.CASCADE)
    vehiculo = models.ForeignKey(
        'Vehiculo', on_delete=models.CASCADE, default=1)
    notificaciones = models.ManyToManyField(
        Notificacion, related_name='procesos')

    def __str__(self):
        return f"{self.fase_proceso} - {self.estado_proceso}"


class Pago(models.Model):
    id_pago = models.AutoField(primary_key=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=50)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    estado_pago = models.CharField(max_length=100)
    proceso = models.ForeignKey('Proceso', on_delete=models.CASCADE)

    def __str__(self):
        return f"Pago {self.id} - {self.estado_pago} - {self.fecha_pago.strftime('%Y-%m-%d')}"


class Cita(models.Model):
    fecha_y_hora = models.DateTimeField()
    motivo = models.TextField()
    ESTADO_CITA_OPCIONES = [
        ('confirmada', 'Confirmada'),
        ('pendiente', 'Pendiente'),
        ('cancelada', 'Cancelada'),
        ('completada', 'Completada'),
    ]
    estado_cita = models.CharField(
        max_length=100, choices=ESTADO_CITA_OPCIONES, default='pendiente')
    ubicacion = models.CharField(max_length=200)
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cita {self.id} - {self.estado_cita} - {self.fecha_y_hora.strftime('%Y-%m-%d %H:%M')}"


class Cotizacion(models.Model):
    ESTADO_CHOICES = (
        ('Pendiente', 'Pendiente'),
        ('Aceptada', 'Aceptada'),
        ('Rechazada', 'Rechazada'),
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE)
    estado = models.CharField(
        max_length=10, choices=ESTADO_CHOICES, default='Pendiente')
    total_estimado = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00)
    descripcion = models.TextField(blank=True, null=True)
    monto_total = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"Cotización {self.id} - {self.estado}"

    def calcular_total_estimado(self):
        # Sumar los costos de todos los detalles de la cotización
        total = self.detallecotizacion_set.aggregate(
            Sum('costo'))['costo__sum'] or 0.00
        self.total_estimado = total
        self.save()


class DetalleCotizacion(models.Model):
    cotizacion = models.ForeignKey(
        Cotizacion, on_delete=models.CASCADE, related_name='detalles')
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE)
    costo_servicio = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.cotizacion} - {self.servicio.nombre_servicio}"


@receiver(post_save, sender=DetalleCotizacion)
def actualizar_total_estimado(sender, instance, **kwargs):
    instance.cotizacion.calcular_total_estimado()


@receiver(post_delete, sender=DetalleCotizacion)
def actualizar_total_estimado_on_delete(sender, instance, **kwargs):
    instance.cotizacion.calcular_total_estimado()
