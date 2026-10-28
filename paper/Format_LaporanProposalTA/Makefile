hooks:
	@chmod +x .hooks/pre-commit
	@git config core.hooksPath .hooks

.PHONY: proposal

clean:
	latexmk -outdir=target -C thesis.tex

compile:
	latexmk -outdir=target -output-format=pdf -pdf thesis.tex

proposal:
	latexmk -outdir=target -jobname=laporan-proposal-dsic2907 -pdf proposal.tex
	cp target/laporan-proposal-dsic2907.pdf Laporan_Proposal_TA_Draft.pdf

record-pkg:
	latex -output-directory=target  -record-package-usages=packages.txt thesis.tex

freeze: record-pkg clean

install-pkg:
	mpm --update-some=packages.txt

pre-commit: record-pkg freeze
