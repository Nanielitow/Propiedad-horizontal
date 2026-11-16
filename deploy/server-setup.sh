#!/usr/bin/env bash
# =============================================================================
#  Preparación de un servidor nuevo (Ubuntu 24.04). Ejecutar UNA vez como root:
#    curl -fsSL https://raw.githubusercontent.com/Nanielitow/Propiedad-horizontal/main/deploy/server-setup.sh | bash
#
#  Qué hace:
#   - Actualiza el sistema e instala Docker (script oficial), git, ufw y fail2ban
#   - Crea el usuario "deploy" (sin contraseña, mismas llaves SSH que root)
#   - SSH solo con llave: desactiva contraseñas y el acceso de root por contraseña
#   - Firewall: solo 22 (SSH), 80 y 443
#   - Swap de 2 GB (picos de memoria del OCR) y actualizaciones de seguridad automáticas
#   - Clona el repositorio en /opt/ph-gestion y programa la copia de seguridad diaria
# =============================================================================
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Nanielitow/Propiedad-horizontal.git}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
APP_DIR="/opt/ph-gestion"

[ "$(id -u)" -eq 0 ] || { echo "Ejecute este script como root"; exit 1; }
[ -s /root/.ssh/authorized_keys ] || { echo "Falta /root/.ssh/authorized_keys: cree el servidor con su llave SSH"; exit 1; }

echo "==> Actualizando el sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw fail2ban unattended-upgrades

echo "==> Docker"
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

echo "==> Usuario de despliegue: $DEPLOY_USER"
id "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"

echo "==> SSH solo con llave"
# Ubuntu 24.04 lee /etc/ssh/sshd_config.d/ en orden alfabético y gana el primer
# valor: el prefijo 00- asegura que esta configuración tenga prioridad
cat > /etc/ssh/sshd_config.d/00-ph-gestion.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl reload ssh

echo "==> Firewall (22, 80, 443)"
# Nota: Docker publica puertos saltándose ufw, por eso en docker-compose.prod.yml
# SOLO Caddy publica puertos (80/443); Postgres y Redis no publican ninguno.
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
systemctl enable --now fail2ban

echo "==> Swap de 2 GB"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
fi

echo "==> Actualizaciones de seguridad automáticas"
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Código en $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
chmod +x "$APP_DIR"/deploy/*.sh

echo "==> Copia de seguridad diaria (03:30 UTC)"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /var/backups/ph-gestion
touch /var/log/ph-gestion-backup.log && chown "$DEPLOY_USER" /var/log/ph-gestion-backup.log
echo "30 3 * * * $DEPLOY_USER $APP_DIR/deploy/backup.sh >> /var/log/ph-gestion-backup.log 2>&1" > /etc/cron.d/ph-gestion-backup

cat <<EOF

Servidor listo. Siguientes pasos (como usuario $DEPLOY_USER):
  ssh $DEPLOY_USER@<IP>
  cd $APP_DIR
  ./deploy/generate-secrets.sh      # crea .env.production con contraseñas aleatorias
  nano .env.production              # complete dominio, R2, Gemini y Resend
  ./deploy/deploy.sh                # primer despliegue
Guía completa: docs/DEPLOY.md
EOF
