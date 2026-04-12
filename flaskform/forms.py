from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DecimalField, DateField, FileField, SelectField, HiddenField
import re
from wtforms.validators import DataRequired, Optional, ValidationError

EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

class MovimientoForm(FlaskForm):
    fecha = DateField('Fecha', validators=[DataRequired()])
    frecuencia = SelectField('Frecuencia', choices=[
        ('una_vez', 'Una vez'),
        ('diario', 'Diario'),
        ('semanal', 'Semanal'),
        ('mensual', 'Mensual')
    ], validators=[DataRequired()])
    descripcion = StringField('Descripción', validators=[DataRequired()])
    valor = DecimalField('Valor', places=2, validators=[DataRequired()])
    categoria_id = StringField('Categoría')

class PrestamoForm(FlaskForm):
    fecha = DateField('Fecha', validators=[DataRequired()])
    frecuencia = SelectField('Frecuencia', choices=[
        ('una_vez', 'Una vez'),
        ('diario', 'Diario'),
        ('semanal', 'Semanal'),
        ('mensual', 'Mensual')
    ], validators=[DataRequired()])
    persona = StringField('Persona', validators=[DataRequired()])
    descripcion = StringField('Descripción', validators=[DataRequired()])
    valor = DecimalField('Valor', places=2, validators=[DataRequired()])

class DeudaForm(FlaskForm):
    fecha = DateField('Fecha', validators=[DataRequired()])
    frecuencia = SelectField('Frecuencia', choices=[
        ('una_vez', 'Una vez'),
        ('diario', 'Diario'),
        ('semanal', 'Semanal'),
        ('mensual', 'Mensual')
    ], validators=[DataRequired()])
    persona = StringField('Persona', validators=[DataRequired()])
    descripcion = StringField('Descripción', validators=[DataRequired()])
    valor = DecimalField('Valor', places=2, validators=[DataRequired()])

class ListaForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired()])
    submit = SubmitField('+')

class LoginForm(FlaskForm):
    usuario = StringField('Nombre de usuario', validators=[DataRequired()])
    clave = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Entrar')


class RegistroForm(FlaskForm):
    usuario = StringField('Nombre de usuario', validators=[DataRequired()])
    correo = StringField('Correo electrónico', validators=[DataRequired()])
    clave = PasswordField('Contraseña', validators=[DataRequired()])
    foto = FileField('Foto de perfil (opcional)')
    submit = SubmitField('Crear cuenta')

    def validate_correo(self, field):
        if not EMAIL_PATTERN.match((field.data or '').strip()):
            raise ValidationError('El correo no tiene un formato válido.')


class DummyForm(FlaskForm):
    pass



class RegistroUnicoForm(FlaskForm):
    tipo = SelectField('Tipo', choices=[
        ('', 'Selecciona un tipo'),
        ('ingreso', 'Ingreso'),
        ('gasto', 'Gasto'),
        ('prestamo', 'Préstamo'),
        ('deuda', 'Deuda')
    ], validators=[DataRequired()])

    fecha = DateField('Fecha', validators=[DataRequired()])
    frecuencia = SelectField('Frecuencia', choices=[
        ('una_vez', 'Una vez'),
        ('diario', 'Diario'),
        ('semanal', 'Semanal'),
        ('mensual', 'Mensual')
    ], validators=[Optional()])

    descripcion = StringField('Descripción', validators=[DataRequired()])
    valor = DecimalField('Valor', places=2, validators=[DataRequired()])
    persona = StringField('Persona', validators=[Optional()])
    categoria = SelectField('Categoría', coerce=int, validators=[], choices=[])

    def validate(self, extra_validators=None):  # <- ACEPTA el argumento
        rv = super().validate(extra_validators=extra_validators)
        if not rv:
            return False

        tipo = self.tipo.data

        if tipo in ['deuda', 'prestamo']:
            if not self.persona.data or self.persona.data.strip() == "":
                self.persona.errors.append('Este campo es obligatorio.')
                return False
            if not self.frecuencia.data:
                self.frecuencia.errors.append('Selecciona una frecuencia.')
                return False

        if tipo in ['ingreso', 'gasto']:
            if not self.categoria.data:
                self.categoria.errors.append('Selecciona una categoría.')
                return False

        return True

    
class CategoriaForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired()])