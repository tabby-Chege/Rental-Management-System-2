from .units import units_bp
from .leases import leases_bp

app.register_blueprint(units_bp)
app.register_blueprint(leases_bp)
