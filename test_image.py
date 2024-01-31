from PIL import Image, ImageDraw
import os
def mark_tile_completion(image_path, row, column):
    # Open the image
    img = Image.open(image_path)

    x_offset = 700
    y_offset = 700
    # width = 1000
    # height = 1000

    # Get image dimensions
    width, height = img.size
    width = width - 2 * x_offset
    height = height - 2 * y_offset
    print(f"{img.size = }")
    print(f"{width = }")
    print(f"{height = }")
    
    line_width = int(width * 0.01 / 2)
    
    # Calculate the dimensions of each bingo tile
    tile_width = width // 5  # Assuming a 5x5 bingo board
    tile_height = height // 5

    print(f"{tile_width = }")
    print(f"{tile_height = }")

    # Calculate the coordinates of the specified bingo tile
    x1 = column * tile_width + x_offset
    y1 = row * tile_height + y_offset
    x2 = (column + 1) * tile_width + x_offset
    y2 = (row + 1) * tile_height + y_offset

    # Create a drawing object
    draw = ImageDraw.Draw(img)

    print(f"{line_width = }")

    # Draw a red square on the specified bingo tile
    draw.rectangle([x1, y1, x2, y2], outline="red", width=line_width)

    # Draw an X on the square
    draw.line([(x1, y1), (x2, y2)], fill="red", width=line_width)
    draw.line([(x1, y2), (x2, y1)], fill="red", width=line_width)

    # Save the modified image
    img.save("marked_bingo_board.png")

# Example usage
image_path = os.path.abspath(r"C:\Users\ADINN-II\Documents\Bingo Discord Bot\images\NOVEMBER_2023_BINGO.png")
marked_row = 5
marked_column = 5

mark_tile_completion(image_path, marked_row - 1, marked_column - 1)
mark_tile_completion("marked_bingo_board.png", marked_row - 1 - 1, marked_column - 1 - 1)

