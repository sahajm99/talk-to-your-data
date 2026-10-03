# Preloaded documents

Three public-domain documents ship with the repository and are indexed at image build time by
`python -m app.ingestion.preload` (see DECISIONS D6). They were downloaded on 2026-09-12 from the
sources below. The eval's gold passages in `eval/questions.json` were verified against these exact
files, so replacing one with a different edition can change the measured numbers.

| File | Work | Source | Rights |
|---|---|---|---|
| `federalist-papers.txt` | The Federalist Papers, by Alexander Hamilton, John Jay and James Madison | Project Gutenberg eBook #1404, https://www.gutenberg.org/ebooks/1404 | Public domain in the United States. The Project Gutenberg header and licence are kept in the file; ingestion strips the wrapper before chunking. |
| `sherlock-holmes.txt` | The Adventures of Sherlock Holmes, by Arthur Conan Doyle | Project Gutenberg eBook #1661, https://www.gutenberg.org/ebooks/1661 | Public domain in the United States. Header and licence kept as above. |
| `nist-sp-800-63-3.pdf` | NIST Special Publication 800-63-3, Digital Identity Guidelines | https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63-3.pdf | A work of the United States federal government, not subject to copyright in the United States. |

Why these three: one novel, one body of argument and one technical standard give the retrieval eval
three different registers, and the PDF exercises the PDF extraction path in production.
