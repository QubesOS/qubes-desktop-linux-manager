default: help

help:
	@echo "Use setup.py to build"
	@echo "Extra make targets available:"
	@echo " install-autostart - install autostart files (xdg, systemd)"
	@echo " install-icons - install icons"
	@echo " install - calls both of the above (but calling setup.py is still necessary)"

install-icons:
	mkdir -p $(DESTDIR)/usr/share/icons/Adwaita/22x22/devices/
	mkdir -p $(DESTDIR)/usr/share/icons/Adwaita/22x22/status/
	cp icons/22x22/generic-usb.png $(DESTDIR)/usr/share/icons/Adwaita/22x22/devices/generic-usb.png
	cp icons/outdated.png $(DESTDIR)/usr/share/icons/Adwaita/22x22/status/
	mkdir -p $(DESTDIR)/usr/share/applications
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/16x16/apps/
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/24x24/apps/
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/32x32/apps/
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/40x40/apps/
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/48x48/apps/
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/72x72/apps/
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/96x96/apps/
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/128x128/apps/
	cp icons/16x16/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/16x16/apps/qui-domains.png
	cp icons/24x24/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/24x24/apps/qui-domains.png
	cp icons/32x32/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/32x32/apps/qui-domains.png
	cp icons/40x40/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/40x40/apps/qui-domains.png
	cp icons/48x48/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/48x48/apps/qui-domains.png
	cp icons/72x72/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/72x72/apps/qui-domains.png
	cp icons/96x96/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/96x96/apps/qui-domains.png
	cp icons/128x128/qui-domains.png $(DESTDIR)/usr/share/icons/hicolor/128x128/apps/qui-domains.png
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/scalable/apps
	cp icons/scalable/*.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/

install-autostart:
	mkdir -p $(DESTDIR)/etc/xdg/autostart
	cp autostart/qubes-device-agent.desktop $(DESTDIR)/etc/xdg/autostart
	cp autostart/qui-domains.desktop $(DESTDIR)/etc/xdg/autostart
	cp autostart/qui-devices.desktop $(DESTDIR)/etc/xdg/autostart
	cp autostart/qui-clipboard.desktop $(DESTDIR)/etc/xdg/autostart
	cp autostart/qui-disk-space.desktop $(DESTDIR)/etc/xdg/autostart
	cp autostart/qui-updates.desktop $(DESTDIR)/etc/xdg/autostart
	mkdir -p $(DESTDIR)/usr/share/applications
	cp desktop/qubes-update-gui.desktop $(DESTDIR)/usr/share/applications/
	mkdir -p $(DESTDIR)/usr/bin
	cp qui/widget-wrapper $(DESTDIR)/usr/bin/widget-wrapper
	mkdir -p $(DESTDIR)/lib/systemd/user/
	cp linux-systemd/qubes-widget@.service $(DESTDIR)/lib/systemd/user/
	cp desktop/qubes-global-config.desktop $(DESTDIR)/usr/share/applications/
	cp desktop/qubes-new-qube.desktop $(DESTDIR)/usr/share/applications/
	cp desktop/qubes-policy-editor-gui.desktop $(DESTDIR)/usr/share/applications/
	install -d $(DESTDIR)/usr/lib/qubes -m 0755
	install -m 0755 qui/devices/qubes-device-agent-autostart $(DESTDIR)/usr/lib/qubes/qubes-device-agent-autostart

install-lang:
	mkdir -p $(DESTDIR)/usr/share/gtksourceview-4/language-specs/
	cp qubes_config/policy_editor/qubes-rpc.lang $(DESTDIR)/usr/share/gtksourceview-4/language-specs/

install: install-autostart install-icons install-lang

.PHONY: clean
clean:
