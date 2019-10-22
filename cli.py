from plotting_test.plotter import main
from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument("-i", "--instr", action="store_true", default=False, help="run cli in instrument mode")

args = vars(parser.parse_args())

if __name__ == '__main__':
    main(instr=args['instr'])

