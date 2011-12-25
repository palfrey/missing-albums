import amazonproduct
from lxml import etree

# AWS, then SECRET, then associate id
keys = [x.strip() for x in file(".amazonkey").readlines()]
amazon = amazonproduct.API(keys[0], keys[1], "uk")

def _empty(album):
	ret = {}
	ret["title"] = album
	ret["url"] = None
	ret["image"] = None
	ret["amazon_new"] = None
	return ret

def searchByTitle(artist, album):
	try:
		root = amazon.item_search("Music", Artist=artist, Title=album, ResponseGroup="Small,ItemAttributes,Images,Offers", AssociateTag = keys[2], MerchantId = "Amazon", Condition = "New")
	except amazonproduct.errors.NoExactMatchesFound:
		return _empty(album)

	page = root.page(1)
	ret = {}

	for item in page.Items.Item:
		binding = item.ItemAttributes.Binding
		if binding!="Audio CD":
			continue

		ret["title"] = item.ItemAttributes.Title
		ret["url"] = item.DetailPageURL
		if hasattr(item, "LargeImage"):
			ret["image"] = item.LargeImage.URL
		else:
			ret["image"] = None
		#ret["lowest_new"] = int(item.OfferSummary.LowestNewPrice.Amount)
		ret["amazon_new"] = int(item.Offers.Offer.OfferListing.Price.Amount)
		return ret
	return _empty(album)
