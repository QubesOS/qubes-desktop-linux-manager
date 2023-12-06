default: help

help:
	@echo "Use setup.py to build"
	@echo "Extra make targets available:"
	@echo " install-autostart - install autostart files (xdg, systemd)"
	@echo " install - calls both of the above (but calling setup.py is still necessary)"

install-autostart:
	mkdir -p $(DESTDIR)/etc/xdg/autostart
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

install-lang:
	mkdir -p $(DESTDIR)/usr/share/gtksourceview-4/language-specs/
	cp qubes_config/policy_editor/qubes-rpc.lang $(DESTDIR)/usr/share/gtksourceview-4/language-specs/

install: install-autostart install-lang

.PHONY: clean
clean:
