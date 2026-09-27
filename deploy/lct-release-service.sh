#!/bin/sh
# Installed root-owned. Fixed verbs only; never accepts caller-provided paths.
set -eu
case "${1-}" in
 restart-test|restart-prod)
   zone=${1#restart-}
   systemctl restart "brutforce-$zone-reference.service" "brutforce-$zone.service"
   systemctl enable "brutforce-$zone-reference.service" "brutforce-$zone.service" >/dev/null ;;
 stop-test|stop-prod)
   zone=${1#stop-}; systemctl stop "brutforce-$zone.service" "brutforce-$zone-reference.service" ;;
 verify-test-f8)
   sha256sum \
     /srv/lct/maks/vision-service/releases/cpu-f8-text-rescue-20260927/night_server.py \
     /srv/lct/maks/vision-service/releases/cpu-ort6-20260926-1/night_server.py \
     /srv/lct/maks/vision-service/releases/cpu-f8-text-rescue-20260927/spec/lexicon.json \
     /srv/lct/maks/vision-service/releases/cpu-f8-text-rescue-20260927/organizer-slugs.json \
     /srv/lct/maks/vision-service/releases/cpu-f8-text-rescue-20260927/visual-neighbors.json \
     /srv/lct/data/vision-retrieval/20260925/detectors/so400m-gatev2/index/index.npz ;;
 start-test-f8) systemctl start lct-vision-test-f8.service ;;
 stop-test-f8) systemctl stop lct-vision-test-f8.service ;;
 backup-prod)
   stamp=$(date -u +%Y%m%dT%H%M%SZ)
   dir=/srv/lct/data/backups/postgres
   umask 077
   runuser -u postgres -- pg_dump -Fc lct_prod > "$dir/lct_prod-$stamp.dump.partial"
   pg_restore --list "$dir/lct_prod-$stamp.dump.partial" >/dev/null
   mv "$dir/lct_prod-$stamp.dump.partial" "$dir/lct_prod-$stamp.dump" ;;
 publish-prod) python3 /usr/local/lib/lct-release/publish-prod.py ;;
 *) exit 2 ;;
esac
