# python_plotting
To install dependencies:
> pip install -r requirements.txt

To run:
> Open terminal
> cd Desktop/python_plotting
> python cli.py -i

To close:
> Open terminal
> cntrl-C

Spins up GUI and pulls data from serial ports to a
multiprocessing queue. Data is displayed in real time across the GUI plots.

To create spec file (for bundling): 
> pyinstaller --windowed --onefile cli.py

To bundle in single application:
> python -m PyInstaller -F --windowed --onefile ./cli.spec
