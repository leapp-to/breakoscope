install:
	cp breakoscope /usr/bin
	mkdir -p /var/lib/breakoscope
	cp -r modules/* /var/lib/breakoscope

uninstall:
	rm /usr/bin/breakoscope
	rm -rf /var/lib/breakoscope
