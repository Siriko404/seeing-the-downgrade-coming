Small test inputs. Firms TSTA, TSTB and TSTC are test names; the numbers are not model output.
finish.py reads data/scores.csv, which this public package does not ship. For the length of a test, the tests copy the
skill's data/ folder to a temporary folder, put this scores.csv in it and point common.DATA at that copy (see the class
made_up_scores in test_credit_watch.py).
