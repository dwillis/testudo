# testudo

**testudo.py** collects class information from the publicly available
[University of Maryland Schedule of Classes]. It includes information such as
the title of the class, the size of the class, enrollment, the time and location
of the class, and the name of the instructor. This repository only makes the
code for assembling the data available. Please email dpwillis@umd.edu with any
questions.

```
git clone https://github.com/dwillis/testudo.git
cd testudo
pipenv install
./testudo.py
```

After it finishes you should find a populated directory structure like this:

    data/{term}/{dept}/{class}.json

For convenience the included **json2csv.py** program will read in all the JSON
files and write out one long CSV file, which is saved in `data/courses.csv`.
Each course JSON file will look something like this:

```javascript
{
  "id": "ANTH222",
  "title": "Introduction to Ecological and Evolutionary Anthropology",
  "credits": "4",
  "description": "Credit only granted for: ANTH220 or ANTH222.",
  "grading-method": [
    "Reg",
    "P-F",
    "Aud"
  ],
  "sections": [
    {
      "id": "0101",
      "instructor": "Barnet Pavao-Zuckerman",
      "seats": "20,",
      "open-seats": "0,",
      "waitlist": "0",
      "days": "TuTh",
      "start": "9:30am",
      "end": "10:45am",
      "building": "ATL",
      "room": "2324"
    },
    {
      "id": "0102",
      "instructor": "Barnet Pavao-Zuckerman",
      "seats": "20,",
      "open-seats": "0,",
      "waitlist": "0",
      "days": "TuTh",
      "start": "9:30am",
      "end": "10:45am",
      "building": "ATL",
      "room": "2324"
    }
  ],
  "term": "201801",
  "department": "Anthropology"
}
```

## Caveats

The included data snapshot does not include the Spring term for 2019 because the crawling was not run in time.

## Tests

There are a few tests, but there should be more.

    pytest test_testudo.py

[University of Maryland Schedule of Classes]: https://app.testudo.umd.edu/soc/
