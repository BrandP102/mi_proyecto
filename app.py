# ============================================================
# IMPORTS
# ============================================================
import os
from datetime import datetime
from flask import (Flask, render_template, request, redirect, 
                   url_for, flash, send_file, session)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, 
                         logout_user, login_required, current_user)
from werkzeug.utils import secure_filename
from weasyprint import HTML
from io import BytesIO
import base64

# ============================================================
# CONFIGURACIÓN DE LA APP
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'mi_clave_secreta_personal_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Usuario único para uso personal
USUARIO_VALIDO = "admin"
CONTRASENA_VALIDA = "admin123"

# ============================================================
# INICIALIZAR EXTENSIONES
# ============================================================
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ============================================================
# MODELO DE BASE DE DATOS
# ============================================================
class Registro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    dependencia = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    fotos = db.Column(db.Text, default="")
    actividad_asociada = db.Column(db.String(1), nullable=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    def lista_fotos(self):
        if self.fotos:
            return [f for f in self.fotos.split(',') if f.strip()]
        return []

# ============================================================
# LOGIN
# ============================================================
class Usuario(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return Usuario(user_id)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
def extension_permitida(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def imagen_a_base64(ruta):
    """Convierte una imagen a base64 para incrustarla en el PDF."""
    try:
        with open(ruta, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except:
        return ""

# ============================================================
# FORMATEO DE FECHAS EN ESPAÑOL
# ============================================================
MESES_ESPANOL = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

def parsear_fecha(fecha_input):
    """Convierte 'YYYY-MM-DD' a objeto date. Devuelve None si falla."""
    if not fecha_input:
        return None
    if isinstance(fecha_input, str):
        try:
            return datetime.strptime(fecha_input, '%Y-%m-%d').date()
        except ValueError:
            return None
    return fecha_input

def formato_largo(fecha_input):
    """'2026-03-25' → '25 de marzo de 2026'"""
    fecha = parsear_fecha(fecha_input)
    if not fecha:
        return fecha_input or ''
    return f"{fecha.day} de {MESES_ESPANOL[fecha.month]} de {fecha.year}"

def formato_mayusculas(fecha_input):
    """'2026-03-25' → '25 DE MARZO DE 2026'"""
    fecha = parsear_fecha(fecha_input)
    if not fecha:
        return (fecha_input or '').upper()
    return f"{fecha.day} DE {MESES_ESPANOL[fecha.month].upper()} DE {fecha.year}"

def formato_periodo(inicio_input, fin_input):
    """
    '2026-02-23', '2026-03-25' →
    'DESDE EL 23 DE (FEBRERO) HASTA EL 25 DE (MARZO) DE 2026'
    """
    inicio = parsear_fecha(inicio_input)
    fin = parsear_fecha(fin_input)
    
    if not inicio or not fin:
        return f"DESDE EL {inicio_input or ''} HASTA EL {fin_input or ''}"
    
    mes_inicio = MESES_ESPANOL[inicio.month].upper()
    mes_fin = MESES_ESPANOL[fin.month].upper()
    
    if inicio.year == fin.year:
        return (f"DESDE EL {inicio.day} DE ({mes_inicio}) "
                f"HASTA EL {fin.day} DE ({mes_fin}) DE {fin.year}")
    else:
        return (f"DESDE EL {inicio.day} DE ({mes_inicio}) DE {inicio.year} "
                f"HASTA EL {fin.day} DE ({mes_fin}) DE {fin.year}")

# ============================================================
# RUTAS
# ============================================================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        contrasena = request.form.get('contrasena')
        if usuario == USUARIO_VALIDO and contrasena == CONTRASENA_VALIDA:
            login_user(Usuario(usuario))
            flash('Bienvenido', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')
    
    query = Registro.query
    if desde:
        try:
            query = query.filter(Registro.fecha >= datetime.strptime(desde, '%Y-%m-%d').date())
        except ValueError:
            pass
    if hasta:
        try:
            query = query.filter(Registro.fecha <= datetime.strptime(hasta, '%Y-%m-%d').date())
        except ValueError:
            pass
    
    registros = query.order_by(Registro.fecha.desc()).all()
    return render_template('dashboard.html', registros=registros, desde=desde, hasta=hasta)

@app.route('/crear', methods=['GET', 'POST'])
@login_required
def crear_registro():
    if request.method == 'POST':
        fecha_str = request.form.get('fecha')
        dependencia = request.form.get('dependencia')
        descripcion = request.form.get('descripcion')
        actividad = request.form.get('actividad_asociada')
        
        if not fecha_str or not dependencia or not descripcion:
            flash('Fecha, dependencia y descripción son obligatorias', 'danger')
            return redirect(url_for('crear_registro'))
        
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        
        nombres_fotos = []
        archivos = request.files.getlist('fotos')
        for archivo in archivos:
            if archivo and archivo.filename and extension_permitida(archivo.filename):
                nombre_seguro = secure_filename(archivo.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
                nombre_final = f"{timestamp}_{nombre_seguro}"
                ruta = os.path.join(app.config['UPLOAD_FOLDER'], nombre_final)
                archivo.save(ruta)
                nombres_fotos.append(nombre_final)
        
        nuevo = Registro(
            fecha=fecha,
            dependencia=dependencia,
            descripcion=descripcion,
            fotos=','.join(nombres_fotos),
            actividad_asociada=actividad if actividad else None
        )
        db.session.add(nuevo)
        db.session.commit()
        
        flash('Registro creado exitosamente', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('crear_registro.html')

@app.route('/eliminar/<int:id>')
@login_required
def eliminar_registro(id):
    registro = Registro.query.get_or_404(id)
    for foto in registro.lista_fotos():
        ruta = os.path.join(app.config['UPLOAD_FOLDER'], foto)
        if os.path.exists(ruta):
            os.remove(ruta)
    db.session.delete(registro)
    db.session.commit()
    flash('Registro eliminado', 'success')
    return redirect(url_for('dashboard'))

# ============================================================
# GENERACIÓN DE PDFs
# ============================================================
@app.route('/pdf/documento1')
@login_required
def generar_pdf_documento1():
    """
    Genera el Documento 1 (tipo ACTIVIDADES.pdf).
    Solo incluye registros cuya fecha esté DENTRO del periodo.
    """
    fecha_principal_raw = request.args.get('fecha_principal', datetime.now().strftime('%Y-%m-%d'))
    periodo_inicio_raw = request.args.get('periodo_inicio', '')
    periodo_fin_raw = request.args.get('periodo_fin', '')
    
    datos = {
        'doctora': request.args.get('doctora', 'YINETH TATHIANA MERA AGUILAR'),
        'num_informe': request.args.get('num_informe', '4'),
        'num_contrato': request.args.get('num_contrato', '1010-12-006-098-2026'),
        'valor': request.args.get('valor', 'NUEVE MILLONES DE PESOS ($9.000.000) M/CTE.'),
        'plazo': request.args.get('plazo', 'CUATRO (04) MESES'),
        'fecha_principal': formato_largo(fecha_principal_raw),
        'fecha_cuadro': formato_mayusculas(fecha_principal_raw),
        'periodo': formato_periodo(periodo_inicio_raw, periodo_fin_raw),
    }
    
    # ============================================================
    # Parsear el rango de fechas del periodo
    # Solo se incluirán actividades cuya fecha esté DENTRO del rango
    # ============================================================
    periodo_inicio = parsear_fecha(periodo_inicio_raw)
    periodo_fin = parsear_fecha(periodo_fin_raw)
    
    literales = [
        ('A', 'Apoyar en el buen funcionamiento de los equipos de cómputo y sus periféricos, de las dependencias de la administración municipal, realizando mantenimiento preventivo y correctivo.',
              'No preste apoyo en el buen funcionamiento de los equipos de cómputo.'),
        ('B', 'Brindar apoyo en el funcionamiento del sistema de redes voz y datos de la entidad realizando mantenimiento preventivo y correctivo.',
              'No preste apoyo en el funcionamiento del sistema de redes voz y datos.'),
        ('C', 'Prestar apoyo en la realización del diagnostico del estado actual de los equipos de computo de las dependencias de la administración.',
              'No preste apoyo en la realizacion del diagnostico del estado actual de los equipos de computos.'),
        ('D', 'Apoyar en la preservación de la seguridad de la información realizando copias de seguridad de los archivos que se reposan en las computadoras de las diferentes dependencias de la administración municipal.',
              'No realice apoyo en la preservación de la seguridad de la información.'),
        ('E', 'Apoyar el profesional universitario en la implementación de la política de gobierno digital de la entidad.',
              'No apoye en la implementación de la política de gobierno digital.'),
        ('F', 'Apoyar el fomento del uso de herramientas tecnológicas en el entorno laboral de la administración.',
              'No apoye el fomento del uso de herramientas tecnológicas.'),
        ('G', 'Apoyar en la automatización de tramites y servicios de la administración municipal en el portal SUIT.',
              'No apoye la automatización de tramites y servicios.'),
        ('H', 'Apoyar en el levantamiento del catalogo de datos y publicación en el portal de datos abiertos.',
              'No apoye en el levantamiento del catalogo de datos.'),
        ('I', 'Apoyar en la publicación de información en el portal web institucional del municipio.',
              'No apoye en la publicación de información en el portal web institucional.'),
        ('J', 'Brindar apoyo técnico a los usuarios internos en materia de recursos informáticos y atender las solicitudes de los mismos en materia de tecnologías de la información y comunicaciones.',
              'No brinde apoyo a los usuarios internos.'),
        ('K', 'Apoyar en la implementación del Plan Estratégico de Tecnologías de la Información – PETI.',
              'No apoye en la implementación del Plan Estratégico de Tecnologías de la Información – PETI.'),
        ('L', 'Cumplir sus obligaciones frente al Sistema de seguridad social conforme lo dispone el articulo 50 de la ley 789 de 2002 y articulo 23 de la ley 1150 de 2007 y demás normas que las modifiquen, aclaren o adicionen.',
              'No cumple con las obligaciones frente al Sistema de seguridad social.'),
        ('M', 'Mantener y guardar reserva de la información de que conozca con ocasión a la ejecución del contrato, excepto cuando sea requerida por las autoridades competentes o persona autorizada.',
              'No mantiene ni guarda reserva de la información.'),
        ('N', 'Contar con los equipos necesarios (computador) para el desarrollo del objeto contractual.',
              'No cuenta con los equipos necesarios para el desarrollo del contrato.'),
        ('O', 'Tener en cuenta las sugerencias que se importan a través del supervisor del contrato.',
              'No tuvo en cuenta las sugerencias.'),
        ('P', 'Reportar en caso de cualquier novedad o anomalía, la situación de manera inmediata al funcionario encargado de supervisión de contrato.',
              'No reporto las novedades o anomalías.'),
        ('Q', 'Las demás actividades que designe el supervisor del contrato y este directamente relacionadas con el objeto del contrato.',
              'No realizo actividades designadas por el supervisor.'),
    ]
    
    # ============================================================
    # Filtrar registros por rango de fechas (periodo)
    # ============================================================
    actividades_por_literal = {}
    for codigo, _, _ in literales:
        query = Registro.query.filter_by(actividad_asociada=codigo)
        
        if periodo_inicio:
            query = query.filter(Registro.fecha >= periodo_inicio)
        if periodo_fin:
            query = query.filter(Registro.fecha <= periodo_fin)
        
        registros = query.order_by(Registro.fecha.asc()).all()
        
        lista = []
        for r in registros:
            fotos_b64 = []
            for foto in r.lista_fotos():
                ruta = os.path.join(app.config['UPLOAD_FOLDER'], foto)
                b64 = imagen_a_base64(ruta)
                if b64:
                    fotos_b64.append(b64)
            lista.append({
                'descripcion': r.descripcion,
                'dependencia': r.dependencia,
                'fotos': fotos_b64
            })
        actividades_por_literal[codigo] = lista
    
    html = render_template('documento1.html',
                           datos=datos,
                           literales=literales,
                           actividades=actividades_por_literal)
    
    pdf = HTML(string=html, base_url=request.base_url).write_pdf()
    
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'Informe_Actividades_{datos["num_informe"]}.pdf'
    )

@app.route('/pdf/documento2')
@login_required
def generar_pdf_documento2():
    """
    Genera el Documento 2 (tipo Imagen 1) con la tabla simple.
    Filtra por rango de fechas (periodo_inicio y periodo_fin).
    """
    periodo_inicio_raw = request.args.get('periodo_inicio', '')
    periodo_fin_raw = request.args.get('periodo_fin', '')
    
    periodo_inicio = parsear_fecha(periodo_inicio_raw)
    periodo_fin = parsear_fecha(periodo_fin_raw)
    
    query = Registro.query
    
    if periodo_inicio:
        query = query.filter(Registro.fecha >= periodo_inicio)
    if periodo_fin:
        query = query.filter(Registro.fecha <= periodo_fin)
    
    registros = query.order_by(Registro.fecha.asc()).all()
    
    html = render_template('documento2.html', registros=registros)
    pdf = HTML(string=html, base_url=request.base_url).write_pdf()
    
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name='Reporte_Actividades.pdf'
    )

# ============================================================
# INICIALIZACIÓN
# ============================================================
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)