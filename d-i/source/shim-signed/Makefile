check:
	mkdir -p build
	# Verifying that the image is signed with the correct key.
	#sbverify --cert cyphermox.crt shimx64.efi.signed
	sbverify --cert MicCorUEFCA2011_2011-06-27.crt $(SHIM_BASE).signed
	# Verifying that we have the correct binary.
	sbattach --detach build/detached-sig $(SHIM_BASE).signed 
	cp /usr/lib/shim/$(SHIM_BASE) build/$(SHIM_BASE).signed
	sbattach --attach build/detached-sig build/$(SHIM_BASE).signed
	cmp $(SHIM_BASE).signed build/$(SHIM_BASE).signed

clean:
	rm -rf build boot.csv BOOT$(EFI_ARCH).CSV
