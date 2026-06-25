# Week 1 Vocabulary Summary

- Issues: 1545
- Total tokens: 77982
- Unique tokens: 6481
- Vocabulary file: `data/processed/vocabulary.csv`

## Highest Frequency Tokens
| token | total_count | document_frequency | percent_of_documents |
| --- | --- | --- | --- |
| simpleclassname | 1656 | 622 | 40.26 |
| container | 1408 | 448 | 29.0 |
| application | 1025 | 400 | 25.89 |
| yarn | 962 | 485 | 31.39 |
| resource | 892 | 346 | 22.39 |
| queue | 858 | 221 | 14.3 |
| support | 780 | 454 | 29.39 |
| node | 776 | 281 | 18.19 |
| use | 776 | 451 | 29.19 |
| rm | 745 | 346 | 22.39 |
| user | 602 | 248 | 16.05 |
| add | 597 | 420 | 27.18 |
| run | 581 | 316 | 20.45 |
| service | 575 | 238 | 15.4 |
| need | 567 | 430 | 27.83 |
| scheduler | 484 | 239 | 15.47 |
| cluster | 474 | 254 | 16.44 |
| methodorvariablename | 456 | 203 | 13.14 |
| nm | 452 | 209 | 13.53 |
| request | 413 | 210 | 13.59 |
| new | 411 | 261 | 16.89 |
| would | 365 | 226 | 14.63 |
| simplemethodorvariablename | 342 | 153 | 9.9 |
| make | 331 | 253 | 16.38 |
| change | 330 | 227 | 14.69 |
| jira | 316 | 279 | 18.06 |
| api | 311 | 186 | 12.04 |
| job | 304 | 144 | 9.32 |
| one | 301 | 208 | 13.46 |
| time | 292 | 193 | 12.49 |
| allow | 289 | 205 | 13.27 |
| file | 285 | 116 | 7.51 |
| create | 280 | 187 | 12.1 |
| log | 277 | 91 | 5.89 |
| set | 276 | 164 | 10.61 |
| client | 276 | 153 | 9.9 |
| currently | 272 | 250 | 16.18 |
| configuration | 272 | 145 | 9.39 |
| get | 266 | 172 | 11.13 |
| provide | 263 | 196 | 12.69 |
| schedule | 260 | 145 | 9.39 |
| app | 250 | 129 | 8.35 |
| could | 249 | 178 | 11.52 |
| like | 244 | 193 | 12.49 |
| capacity | 239 | 122 | 7.9 |
| base | 233 | 178 | 11.52 |
| state | 228 | 112 | 7.25 |
| start | 214 | 134 | 8.67 |
| task | 213 | 108 | 6.99 |
| different | 213 | 142 | 9.19 |

## Candidate Tokens To Remove
These are mostly Rust-cleaner marker tokens or project-generic terms. Treat them as review candidates before removing them from LDA input.

| token | total_count | document_frequency | percent_documents | candidate_class | reason |
| --- | --- | --- | --- | --- | --- |
| simpleclassname | 1656 | 622 | 40.26 | Marker | Rust cleaner marker token; review for removal before LDA |
| methodorvariablename | 456 | 203 | 13.14 | Marker | Rust cleaner marker token; review for removal before LDA |
| simplemethodorvariablename | 342 | 153 | 9.9 | Marker | Rust cleaner marker token; review for removal before LDA |
| classname | 106 | 43 | 2.78 | Marker | Rust cleaner marker token; review for removal before LDA |
| versionnumber | 106 | 42 | 2.72 | Marker | Rust cleaner marker token; review for removal before LDA |
| filepath | 87 | 44 | 2.85 | Marker | Rust cleaner marker token; review for removal before LDA |
| structuredcodeblock | 72 | 48 | 3.11 | Marker | Rust cleaner marker token; review for removal before LDA |
| githublink | 57 | 18 | 1.17 | Marker | Rust cleaner marker token; review for removal before LDA |
| weblink | 55 | 43 | 2.78 | Marker | Rust cleaner marker token; review for removal before LDA |
| userprofilelink | 51 | 24 | 1.55 | Marker | Rust cleaner marker token; review for removal before LDA |
| noformatblock | 23 | 10 | 0.65 | Marker | Rust cleaner marker token; review for removal before LDA |
| package | 19 | 14 | 0.91 | Marker | Rust cleaner marker token; review for removal before LDA |
| issuelink | 15 | 13 | 0.84 | Marker | Rust cleaner marker token; review for removal before LDA |
| inlinecodesample | 14 | 11 | 0.71 | Marker | Rust cleaner marker token; review for removal before LDA |
| imageattachment | 12 | 7 | 0.45 | Marker | Rust cleaner marker token; review for removal before LDA |
| attachment | 10 | 5 | 0.32 | Marker | Rust cleaner marker token; review for removal before LDA |

## Candidate Tokens To Replace With Ontology Classes
These are exact matches in the ontology workbook. They should be reviewed before replacement because project-specific terms can be meaningful.

| token | total_count | document_frequency | percent_documents | candidate_class |
| --- | --- | --- | --- | --- |
| application | 1025 | 400 | 25.89 | Component |
| queue | 858 | 221 | 14.3 | Component|Pattern |
| node | 776 | 281 | 18.19 | Technology |
| user | 602 | 248 | 16.05 | Component |
| service | 575 | 238 | 15.4 | Component |
| request | 413 | 210 | 13.59 | Connector_Data |
| change | 330 | 227 | 14.69 | Connector |
| api | 311 | 186 | 12.04 | Component|Technology |
| job | 304 | 144 | 9.32 | Component |
| file | 285 | 116 | 7.51 | Component |
| log | 277 | 91 | 5.89 | Requirement |
| client | 276 | 153 | 9.9 | Component|Pattern |
| get | 266 | 172 | 11.13 | Connector |
| app | 250 | 129 | 8.35 | Component |
| task | 213 | 108 | 6.99 | Connector_Data |
| implement | 200 | 152 | 9.84 | Connector |
| process | 200 | 91 | 5.89 | Component |
| data | 195 | 119 | 7.7 | Connector_Data |
| store | 191 | 112 | 7.25 | Component|Connector |
| policy | 190 | 90 | 5.83 | Requirement |
| rest | 189 | 113 | 7.31 | Pattern|Technology |
| case | 181 | 140 | 9.06 | Requirement |
| docker | 177 | 56 | 3.62 | Technology |
| event | 176 | 61 | 3.95 | Component |
| information | 169 | 115 | 7.44 | Connector_Data |
| heartbeat | 166 | 72 | 4.66 | Pattern |
| call | 163 | 95 | 6.15 | Connector|Connector_Data |
| server | 159 | 89 | 5.76 | Component|Pattern |
| share | 156 | 71 | 4.6 | Connector |
| list | 154 | 94 | 6.08 | Connector_Data |
| apps | 149 | 93 | 6.02 | Component |
| entity | 137 | 48 | 3.11 | Component |
| hadoop | 130 | 73 | 4.72 | Technology |
| interface | 129 | 83 | 5.37 | Component |
| framework | 127 | 71 | 4.6 | Technology |
| class | 125 | 69 | 4.47 | Component |
| hdfs | 122 | 69 | 4.47 | Technology |
| available | 117 | 91 | 5.89 | Quality_Attribute |
| write | 117 | 75 | 4.85 | Connector |
| cache | 113 | 43 | 2.78 | Pattern |
| good | 108 | 97 | 6.28 | Quality_Attribute |
| system | 106 | 71 | 4.6 | Component |
| token | 104 | 42 | 2.72 | Connector_Data |
| value | 103 | 51 | 3.3 | Requirement |
| logic | 97 | 64 | 4.14 | Component |
| check | 96 | 62 | 4.01 | Connector |
| access | 95 | 57 | 3.69 | Connector |
| map | 94 | 52 | 3.37 | Connector_Data |
| component | 93 | 49 | 3.17 | Component |
| method | 92 | 44 | 2.85 | Component |

## Project-Specific Or Dominant Tokens
These frequent tokens may dominate topics and should be reviewed after the first LDA run.

| token | total_count | document_frequency | percent_documents | reason |
| --- | --- | --- | --- | --- |
| yarn | 962 | 485 | 31.39 | project name; often too broad for topic modeling |
| jira | 316 | 279 | 18.06 | issue-tracker term; often too broad for topic modeling |
| container | 1408 | 448 | 29.0 | High-frequency token without exact ontology match |
| resource | 892 | 346 | 22.39 | High-frequency token without exact ontology match |
| support | 780 | 454 | 29.39 | High-frequency token without exact ontology match |
| use | 776 | 451 | 29.19 | High-frequency token without exact ontology match |
| rm | 745 | 346 | 22.39 | High-frequency token without exact ontology match |
| add | 597 | 420 | 27.18 | High-frequency token without exact ontology match |
| run | 581 | 316 | 20.45 | High-frequency token without exact ontology match |
| need | 567 | 430 | 27.83 | High-frequency token without exact ontology match |
| scheduler | 484 | 239 | 15.47 | High-frequency token without exact ontology match |
| cluster | 474 | 254 | 16.44 | High-frequency token without exact ontology match |
| nm | 452 | 209 | 13.53 | High-frequency token without exact ontology match |
| new | 411 | 261 | 16.89 | High-frequency token without exact ontology match |
| would | 365 | 226 | 14.63 | High-frequency token without exact ontology match |
| make | 331 | 253 | 16.38 | High-frequency token without exact ontology match |
| one | 301 | 208 | 13.46 | High-frequency token without exact ontology match |
| time | 292 | 193 | 12.49 | High-frequency token without exact ontology match |
| allow | 289 | 205 | 13.27 | High-frequency token without exact ontology match |
| create | 280 | 187 | 12.1 | High-frequency token without exact ontology match |
| set | 276 | 164 | 10.61 | High-frequency token without exact ontology match |
| currently | 272 | 250 | 16.18 | High-frequency token without exact ontology match |
| configuration | 272 | 145 | 9.39 | High-frequency token without exact ontology match |
| provide | 263 | 196 | 12.69 | High-frequency token without exact ontology match |
| schedule | 260 | 145 | 9.39 | High-frequency token without exact ontology match |
| could | 249 | 178 | 11.52 | High-frequency token without exact ontology match |
| like | 244 | 193 | 12.49 | High-frequency token without exact ontology match |
| capacity | 239 | 122 | 7.9 | High-frequency token without exact ontology match |
| base | 233 | 178 | 11.52 | High-frequency token without exact ontology match |
| state | 228 | 112 | 7.25 | High-frequency token without exact ontology match |
| start | 214 | 134 | 8.67 | High-frequency token without exact ontology match |
| different | 213 | 142 | 9.19 | High-frequency token without exact ontology match |
| also | 198 | 174 | 11.26 | High-frequency token without exact ontology match |
| timeline | 198 | 97 | 6.28 | High-frequency token without exact ontology match |
| work | 197 | 146 | 9.45 | High-frequency token without exact ontology match |
| implementation | 189 | 138 | 8.93 | High-frequency token without exact ontology match |
| type | 184 | 86 | 5.57 | High-frequency token without exact ontology match |
| memory | 183 | 84 | 5.44 | High-frequency token without exact ontology match |
| launch | 182 | 94 | 6.08 | High-frequency token without exact ontology match |
| allocate | 179 | 114 | 7.38 | High-frequency token without exact ontology match |
| may | 176 | 134 | 8.67 | High-frequency token without exact ontology match |
| allocation | 174 | 109 | 7.06 | High-frequency token without exact ontology match |
| current | 171 | 149 | 9.64 | High-frequency token without exact ontology match |
| restart | 171 | 87 | 5.63 | High-frequency token without exact ontology match |
| multiple | 169 | 124 | 8.03 | High-frequency token without exact ontology match |
| label | 167 | 50 | 3.24 | High-frequency token without exact ontology match |
| preemption | 166 | 58 | 3.75 | High-frequency token without exact ontology match |
| track | 166 | 141 | 9.13 | High-frequency token without exact ontology match |
| example | 162 | 129 | 8.35 | High-frequency token without exact ontology match |
| issue | 161 | 118 | 7.64 | High-frequency token without exact ontology match |
