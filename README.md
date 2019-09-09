# python_plotting
To install dependencies:
> pip install -r requirements.txt

To run:
> python cli.py

Spins up GUI and 3 scripts (co2.py, nox.py, bc.py) which send dummy data to a
multiprocessing queue. Data is displayed in real time across the GUI plots.

To create spec file (for bundling): 
> pyinstaller --windowed --onefile cli.py

To bundle in single application:
> python -m PyInstaller -F --windowed --onefile ./cli.spec
