from routes.units import units_bp
from routes.leases import leases_bp

app.register_blueprint(units_bp)
app.register_blueprint(leases_bp)