PAT=error
PAT=.
eslint:
	for fname in *.js ; do echo $$fname ; npx eslint --config eslint.config $$fname | sed "s/:[0-9][0-9]//" | sed "s=^ *=$$fname: =" | grep $(PAT) ; done
