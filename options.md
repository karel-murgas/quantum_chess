# Split
## Split on move
- every move causes new split
- player can choose when to split and when not
## What splits
- only currently moved figure is split (even where it is already in superposition)
- every figures in superposition with currently moved figure split
## How is probability calculated?
- every figure in superposition has 1/n probability, where n is number of figures in that superposition
- every figure has half the probability of it's "parent" figure
# Movement
## Who moves
- Only current figure move
- Only current figure and it's newest superposition (in case it splits this turn) move
- All figures in superpositon move
## How are other figures in superposition moved
- any legal movement
- symetric by the middle line (left-right symetry)
- symetric by the middle point
## What happens if figure should move out of the board?
- you can't play that move (even main figure can't move)¨
- confliction figure doesn't move, others do move
- conflictiong figure moves as close to the border as is legal (given her movement rules)
## What happens if figure should move into own figure (not in it's superposition)?
- you can't play that move (even main figure can't move)¨
- confliction figure doesn't move, others do move
- conflictiong figure moves as close to the border as is legal (given her movement rules)
- it takes out own figure
## What happens if it moves to it's own superposition figure?
- They merge and sum their probabilities
# Wave function collapse (always on contact with other figure)
- Only current figure is evaluated - if not there, other probabilities are recalculated, if is there, other figures disappear
- It's shown where figure is and other figures in superposition disappear